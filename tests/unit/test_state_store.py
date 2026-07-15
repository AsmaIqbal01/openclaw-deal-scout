"""
T018 — Unit tests for gmail_intake.state_store.

Covers:
  - read_store: missing file, corrupted JSON, malformed last_poll_time
  - acquire_lock: concurrent invocation conflict
  - append_message: atomic write with no leftover .tmp file
"""
import json
import os

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
