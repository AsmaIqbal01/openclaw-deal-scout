"""
T018 + T025 — Unit tests for gmail_intake.state_store.

Covers:
  - read_store: missing file, corrupted JSON, malformed last_poll_time
  - acquire_lock: concurrent invocation conflict
  - append_message: atomic write with no leftover .tmp file
  - T025: crash-recovery (.tmp leftover ignored), already_processed set identity
"""
import json
import os
from unittest.mock import patch

import pytest

from gmail_intake.models import (
    ConcurrentInvocationError,
    ProcessedMessage,
    StateStore,
    StateStoreReadError,
)
from gmail_intake.state_store import acquire_lock, append_message, read_store


# ---------------------------------------------------------------------------
# read_store
# ---------------------------------------------------------------------------


def test_read_store_missing_file(tmp_path):
    path = str(tmp_path / "state.json")
    store = read_store(path)
    assert store.last_poll_time is None
    assert store.messages == []


def test_read_store_corrupted_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json{", encoding="utf-8")
    with pytest.raises(StateStoreReadError):
        read_store(str(path))


def test_read_store_malformed_poll_time(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"last_poll_time": "not-a-date", "messages": []}),
        encoding="utf-8",
    )
    store = read_store(str(path))
    # Malformed value is treated as None — no exception raised
    assert store.last_poll_time is None
    assert store.messages == []


# ---------------------------------------------------------------------------
# acquire_lock
# ---------------------------------------------------------------------------


def test_acquire_lock_conflict(tmp_path):
    store_path = str(tmp_path / "state.json")
    lock = acquire_lock(store_path)
    try:
        with pytest.raises(ConcurrentInvocationError):
            acquire_lock(store_path)
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# append_message
# ---------------------------------------------------------------------------


def test_append_message_atomic(tmp_path):
    store_path = str(tmp_path / "state.json")
    store = StateStore(last_poll_time=None)
    entry = ProcessedMessage(
        gmail_message_id="msg123",
        processed_at="2026-07-10T12:00:00+00:00",
        outcome="deal_extracted",
    )

    append_message(store_path, store, entry)

    # Canonical store file must exist and contain the entry
    assert os.path.exists(store_path)
    with open(store_path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(data["messages"]) == 1
    assert data["messages"][0]["gmail_message_id"] == "msg123"
    assert data["messages"][0]["outcome"] == "deal_extracted"

    # No leftover .tmp file in the same directory
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == [], f"Unexpected .tmp files: {leftover}"


# ---------------------------------------------------------------------------
# T025 — crash-recovery and pre-filter
# ---------------------------------------------------------------------------


def test_append_message_no_tmp_on_success(tmp_path):
    """After a successful append_message the temp file is always renamed away."""
    store_path = str(tmp_path / "state.json")
    store = StateStore(last_poll_time=None)
    entry = ProcessedMessage(
        gmail_message_id="msg-tmp-check",
        processed_at="2026-07-10T12:00:00+00:00",
        outcome="deal_extracted",
    )

    append_message(store_path, store, entry)

    assert list(tmp_path.glob("*.tmp")) == []


def test_append_message_crash_recovery(tmp_path):
    """
    A leftover .tmp file from a previous crashed write does not corrupt read_store.

    Scenario: the canonical store has one committed entry; a stale .tmp file
    (different content) is present in the same directory. read_store must return
    only the canonical committed state.
    """
    store_path = str(tmp_path / "state.json")
    committed_entry = ProcessedMessage(
        gmail_message_id="committed-msg",
        processed_at="2026-07-10T12:00:00+00:00",
        outcome="deal_extracted",
    )

    # Write the committed canonical state
    store = StateStore(last_poll_time=None)
    append_message(store_path, store, committed_entry)

    # Simulate a crashed write: leave a .tmp file with different content
    stale_tmp = tmp_path / "stale_write.tmp"
    stale_tmp.write_text(
        json.dumps({"last_poll_time": None, "messages": [
            {"gmail_message_id": "ghost-msg",
             "processed_at": "2026-07-11T00:00:00+00:00",
             "outcome": "deal_extracted"},
        ]}),
        encoding="utf-8",
    )

    recovered = read_store(store_path)

    assert len(recovered.messages) == 1
    assert recovered.messages[0].gmail_message_id == "committed-msg"


def test_read_store_already_processed_set(tmp_path):
    """After two append_message calls the already_processed set contains exactly 2 IDs."""
    store_path = str(tmp_path / "state.json")
    store = StateStore(last_poll_time=None)

    append_message(
        store_path, store,
        ProcessedMessage(
            gmail_message_id="alpha",
            processed_at="2026-07-10T10:00:00+00:00",
            outcome="deal_extracted",
        ),
    )
    append_message(
        store_path, store,
        ProcessedMessage(
            gmail_message_id="beta",
            processed_at="2026-07-10T11:00:00+00:00",
            outcome="not_a_deal",
        ),
    )

    fresh = read_store(store_path)
    already_processed = {m.gmail_message_id for m in fresh.messages}

    assert already_processed == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# T031 — SC-004 #12: state store write failure
# ---------------------------------------------------------------------------


def test_append_message_write_failure(tmp_path):
    """SC-004 #12: OSError during atomic rename is swallowed; append_message does not raise."""
    store_path = str(tmp_path / "state.json")
    store = StateStore(last_poll_time=None)
    entry = ProcessedMessage(
        gmail_message_id="msg-fail",
        processed_at="2026-07-10T12:00:00+00:00",
        outcome="deal_extracted",
    )

    with patch("gmail_intake.state_store.os.replace", side_effect=OSError("disk full")):
        # Must not raise — OSError is caught and logged as WARN
        append_message(store_path, store, entry)

    # Canonical store file must NOT exist (os.replace never completed)
    assert not os.path.exists(store_path)
