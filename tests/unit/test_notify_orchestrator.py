"""Tests for discord_notifier.orchestrator — T012 (US1), T015 (US2), T018 (US3), T019, T021."""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from discord_notifier.orchestrator import run_notify_cycle

_BASE_ENTRY = {
    "gmail_message_id": "msg-001",
    "sender_email": "alice@example.com",
    "sender_name": "Alice",
    "subject": "Deal proposal",
    "received_at": "2026-07-17T09:00:00Z",
    "deal_summary": "A new deal.",
    "deal_category": "partnership_inquiry",
    "confidence_score": 0.9,
    "raw_email_excerpt": None,
    "status": "crm-logged",
}


def _write_store(path, messages):
    data = {"last_poll_time": None, "messages": messages}
    with open(path, "w") as fh:
        json.dump(data, fh)


def _read_store(path):
    return json.loads(open(path).read())


def _noop_env():
    return {"NOTIFIER": "noop"}


# ── T012 US1: happy path ──────────────────────────────────────────────────────

def test_cycle_single_deal_returns_ok_and_counts(tmp_path):
    """One crm-logged entry + noop adapter → status=ok, discord_notified=1."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_BASE_ENTRY])
    result = run_notify_cycle(str(p), env=_noop_env())
    assert result.status == "ok"
    assert result.discord_notified == 1
    assert result.notify_pending == 0
    assert result.skipped == 0


def test_cycle_empty_store_returns_ok_zero_counts(tmp_path):
    """Empty state store → status=ok, all counts zero."""
    p = tmp_path / "store.json"
    _write_store(str(p), [])
    result = run_notify_cycle(str(p), env=_noop_env())
    assert result.status == "ok"
    assert result.discord_notified == 0


def test_cycle_multiple_deals_all_notified(tmp_path):
    """Three crm-logged entries → discord_notified=3."""
    entries = [
        {**_BASE_ENTRY, "gmail_message_id": f"msg-{i:03d}", "status": "crm-logged"}
        for i in range(3)
    ]
    p = tmp_path / "store.json"
    _write_store(str(p), entries)
    result = run_notify_cycle(str(p), env=_noop_env())
    assert result.discord_notified == 3


def test_cycle_absent_state_file_returns_ok(tmp_path):
    """Absent state file is treated as empty store → status=ok, all counts zero."""
    p = tmp_path / "nonexistent.json"
    result = run_notify_cycle(str(p), env=_noop_env())
    assert result.status == "ok"
    assert result.discord_notified == 0


def test_cycle_updates_state_store_on_disk(tmp_path):
    """After a successful cycle, the state store on disk reflects discord-notified."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_BASE_ENTRY])
    run_notify_cycle(str(p), env=_noop_env())
    store = _read_store(str(p))
    entry = store["messages"][0]
    assert entry["status"] == "discord-notified"
    assert "notified_at" in entry


# ── T015 US2: idempotency ─────────────────────────────────────────────────────

def test_cycle_skips_already_notified_entries(tmp_path):
    """Mix of discord-notified and crm-logged → notified=1, skipped=1."""
    notified = {**_BASE_ENTRY, "gmail_message_id": "msg-001", "status": "discord-notified"}
    pending = {**_BASE_ENTRY, "gmail_message_id": "msg-002", "status": "crm-logged"}
    p = tmp_path / "store.json"
    _write_store(str(p), [notified, pending])
    result = run_notify_cycle(str(p), env=_noop_env())
    assert result.discord_notified == 1
    assert result.skipped == 1


def test_cycle_double_run_second_all_skipped(tmp_path):
    """Two cycles in a row → second cycle reports discord_notified=0, skipped=1."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_BASE_ENTRY])
    run_notify_cycle(str(p), env=_noop_env())
    result2 = run_notify_cycle(str(p), env=_noop_env())
    assert result2.discord_notified == 0
    assert result2.skipped == 1


def test_cycle_mixed_batch_counts_correctly(tmp_path):
    """3 entries: 1 notified, 1 crm-logged, 1 pending → skipped=1, notified=2."""
    entries = [
        {**_BASE_ENTRY, "gmail_message_id": "msg-001", "status": "discord-notified"},
        {**_BASE_ENTRY, "gmail_message_id": "msg-002", "status": "crm-logged"},
        {**_BASE_ENTRY, "gmail_message_id": "msg-003", "status": "crm-logged-notify-pending"},
    ]
    p = tmp_path / "store.json"
    _write_store(str(p), entries)
    result = run_notify_cycle(str(p), env=_noop_env())
    assert result.skipped == 1
    assert result.discord_notified == 2


# ── T018 US3: drain-first and failure paths ───────────────────────────────────

def test_cycle_drain_first_pending_before_ready(tmp_path):
    """Drain-first: pending entries are notified before crm-logged entries."""
    call_order = []

    class TrackingAdapter:
        def notify(self, deal):
            call_order.append(deal["gmail_message_id"])
            return "discord-notified"

    pending = {**_BASE_ENTRY, "gmail_message_id": "msg-pending", "status": "crm-logged-notify-pending"}
    ready = {**_BASE_ENTRY, "gmail_message_id": "msg-ready", "status": "crm-logged"}
    p = tmp_path / "store.json"
    _write_store(str(p), [ready, pending])  # ready listed first — drain-first must reorder

    with patch("discord_notifier.orchestrator.get_adapter", return_value=TrackingAdapter()):
        run_notify_cycle(str(p), env=_noop_env())

    assert call_order[0] == "msg-pending", "pending must be processed before ready"
    assert call_order[1] == "msg-ready"


def test_cycle_one_fail_one_succeed_counts_both(tmp_path):
    """One deal fails (pending), one succeeds → notified=1, pending=1."""
    class PartialAdapter:
        def __init__(self):
            self._call = 0

        def notify(self, deal):
            self._call += 1
            return "discord-notified" if self._call % 2 == 0 else "crm-logged-notify-pending"

    entries = [
        {**_BASE_ENTRY, "gmail_message_id": "msg-001", "status": "crm-logged"},
        {**_BASE_ENTRY, "gmail_message_id": "msg-002", "status": "crm-logged"},
    ]
    p = tmp_path / "store.json"
    _write_store(str(p), entries)
    with patch("discord_notifier.orchestrator.get_adapter", return_value=PartialAdapter()):
        result = run_notify_cycle(str(p), env=_noop_env())
    assert result.discord_notified + result.notify_pending == 2


def test_cycle_all_fail_all_pending(tmp_path):
    """All deals fail → notify_pending equals entry count."""
    class FailAdapter:
        def notify(self, deal):
            return "crm-logged-notify-pending"

    entries = [
        {**_BASE_ENTRY, "gmail_message_id": f"msg-{i:03d}", "status": "crm-logged"}
        for i in range(3)
    ]
    p = tmp_path / "store.json"
    _write_store(str(p), entries)
    with patch("discord_notifier.orchestrator.get_adapter", return_value=FailAdapter()):
        result = run_notify_cycle(str(p), env=_noop_env())
    assert result.notify_pending == 3
    assert result.discord_notified == 0


def test_cycle_invalid_json_returns_error(tmp_path):
    """Corrupted JSON in state store → status=error, cycle does not raise."""
    p = tmp_path / "store.json"
    p.write_text("{ not valid json")
    result = run_notify_cycle(str(p), env=_noop_env())
    assert result.status == "error"
    assert result.error_details


def test_cycle_per_deal_exception_counted_as_pending(tmp_path):
    """Unexpected exception in notify_deal → counted as pending, cycle continues."""
    class BombAdapter:
        def notify(self, deal):
            raise RuntimeError("unexpected crash")

    p = tmp_path / "store.json"
    _write_store(str(p), [_BASE_ENTRY])
    with patch("discord_notifier.orchestrator.get_adapter", return_value=BombAdapter()):
        result = run_notify_cycle(str(p), env=_noop_env())
    assert result.status == "ok"
    assert result.notify_pending == 1


# ── T019: concurrent invocation ───────────────────────────────────────────────

def test_cycle_concurrent_invocation_returns_error(tmp_path):
    """Second concurrent cycle is blocked by lock → status=error."""
    from discord_notifier.models import NotifyConcurrentError

    p = tmp_path / "store.json"
    _write_store(str(p), [])
    with patch(
        "discord_notifier.orchestrator.acquire_lock",
        side_effect=NotifyConcurrentError("concurrent"),
    ):
        result = run_notify_cycle(str(p), env=_noop_env())
    assert result.status == "error"
    assert "concurrent" in (result.error_details or "").lower()


# ── T021: NOTIFIER env-var resolution ─────────────────────────────────────────

def test_cycle_missing_notifier_env_returns_error(tmp_path):
    """Missing NOTIFIER env var → status=error, error_details mentions NOTIFIER."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_BASE_ENTRY])
    result = run_notify_cycle(str(p), env={})
    assert result.status == "error"
    assert "NOTIFIER" in (result.error_details or "")


def test_cycle_notifier_name_overrides_env(tmp_path):
    """notifier_name kwarg takes precedence over NOTIFIER in env."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_BASE_ENTRY])
    # env has NOTIFIER=discord (would fail without a webhook URL),
    # but explicit kwarg noop must win
    result = run_notify_cycle(str(p), notifier_name="noop", env={"NOTIFIER": "discord"})
    assert result.status == "ok"
    assert result.discord_notified == 1


def test_cycle_unknown_notifier_returns_error(tmp_path):
    """Unknown notifier name → status=error."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_BASE_ENTRY])
    result = run_notify_cycle(str(p), env={"NOTIFIER": "unknown_adapter"})
    assert result.status == "error"
