"""Tests for discord_notifier.state_store — T004."""
import json
import os

import pytest

from discord_notifier.models import NotifyStateStoreReadError
from discord_notifier.state_store import (
    _merge_write,
    _raw_load,
    get_pending_notifications,
    get_ready_to_notify,
    read_notify_store,
    write_notify_outcome,
)

_ENTRY_LOGGED = {
    "gmail_message_id": "msg-001",
    "processed_at": "2026-07-17T09:00:00Z",
    "outcome": "deal_extracted",
    "status": "crm-logged",
    "sender_email": "a@example.com",
    "sender_name": "Alice",
    "subject": "Partnership inquiry",
    "received_at": "2026-07-17T08:00:00Z",
    "deal_summary": "Alice wants to discuss a partnership.",
    "deal_category": "partnership_inquiry",
    "confidence_score": 0.9,
    "raw_email_excerpt": None,
}

_ENTRY_PENDING = {**_ENTRY_LOGGED, "gmail_message_id": "msg-002", "status": "crm-logged-notify-pending"}
_ENTRY_NOTIFIED = {**_ENTRY_LOGGED, "gmail_message_id": "msg-003", "status": "discord-notified"}
_ENTRY_NOT_DEAL = {**_ENTRY_LOGGED, "gmail_message_id": "msg-004", "status": "not_a_deal"}


def _write_store(path, messages, extra_top_level=None):
    data = {"last_poll_time": None, "messages": messages}
    if extra_top_level:
        data.update(extra_top_level)
    with open(path, "w") as fh:
        json.dump(data, fh)


# T1: _raw_load on absent file → default skeleton
def test_raw_load_absent_file(tmp_path):
    result = _raw_load(str(tmp_path / "missing.json"))
    assert result == {"last_poll_time": None, "messages": []}


# T2: _raw_load on valid JSON → parsed dict
def test_raw_load_valid_json(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [_ENTRY_LOGGED])
    result = _raw_load(str(p))
    assert result["messages"][0]["gmail_message_id"] == "msg-001"


# T3: read_notify_store preserves all top-level keys including consecutive_401_cycles
def test_read_notify_store_preserves_extra_keys(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [], extra_top_level={"consecutive_401_cycles": 2, "custom_key": "kept"})
    result = read_notify_store(str(p))
    assert result["consecutive_401_cycles"] == 2
    assert result["custom_key"] == "kept"


# T4: get_ready_to_notify returns only crm-logged entries
def test_get_ready_to_notify_filters_correctly(tmp_path):
    store = {"messages": [_ENTRY_LOGGED, _ENTRY_PENDING, _ENTRY_NOTIFIED, _ENTRY_NOT_DEAL]}
    result = get_ready_to_notify(store)
    assert len(result) == 1
    assert result[0]["gmail_message_id"] == "msg-001"


# T5: get_pending_notifications returns only crm-logged-notify-pending entries
def test_get_pending_notifications_filters_correctly(tmp_path):
    store = {"messages": [_ENTRY_LOGGED, _ENTRY_PENDING, _ENTRY_NOTIFIED]}
    result = get_pending_notifications(store)
    assert len(result) == 1
    assert result[0]["gmail_message_id"] == "msg-002"


# T6: get_ready_to_notify on empty store → empty list
def test_get_ready_to_notify_empty_store():
    assert get_ready_to_notify({"messages": []}) == []


# T7: get_pending_notifications on empty store → empty list
def test_get_pending_notifications_empty_store():
    assert get_pending_notifications({"messages": []}) == []


# T8: write_notify_outcome with discord-notified and notified_at
def test_write_notify_outcome_success_path(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [_ENTRY_LOGGED])
    write_notify_outcome(str(p), "msg-001", "discord-notified", notified_at="2026-07-17T10:00:00Z")
    result = json.loads(p.read_text())
    entry = result["messages"][0]
    assert entry["status"] == "discord-notified"
    assert entry["notified_at"] == "2026-07-17T10:00:00Z"
    assert entry["sender_email"] == "a@example.com"  # existing fields preserved


# T9: write_notify_outcome with crm-logged-notify-pending and notify_error_reason
def test_write_notify_outcome_failure_path(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [_ENTRY_LOGGED])
    write_notify_outcome(str(p), "msg-001", "crm-logged-notify-pending", notify_error_reason="500 Internal Server Error")
    result = json.loads(p.read_text())
    entry = result["messages"][0]
    assert entry["status"] == "crm-logged-notify-pending"
    assert entry["notify_error_reason"] == "500 Internal Server Error"
    assert "notified_at" not in entry


# T10: _merge_write preserves consecutive_401_cycles top-level key
def test_merge_write_preserves_consecutive_401_cycles(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [], extra_top_level={"consecutive_401_cycles": 3})
    _merge_write(str(p), {"last_poll_time": "2026-07-17T10:00:00Z"})
    result = json.loads(p.read_text())
    assert result["consecutive_401_cycles"] == 3
    assert result["last_poll_time"] == "2026-07-17T10:00:00Z"


# T11: write_notify_outcome on non-existent gmail_message_id → KeyError
def test_write_notify_outcome_missing_id_raises(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [_ENTRY_LOGGED])
    with pytest.raises(KeyError, match="msg-999"):
        write_notify_outcome(str(p), "msg-999", "discord-notified")
