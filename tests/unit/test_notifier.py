"""Tests for discord_notifier.notifier — T010 (US1), T014 (US2), T017 (US3)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from discord_notifier.adapter import NoopAdapter
from discord_notifier.notifier import notify_deal

_DEAL = {
    "gmail_message_id": "msg-001",
    "sender_email": "alice@example.com",
    "sender_name": "Alice",
    "subject": "Partnership proposal",
    "received_at": "2026-07-17T09:00:00Z",
    "deal_summary": "Alice proposes a joint venture.",
    "deal_category": "partnership_inquiry",
    "confidence_score": 0.88,
    "raw_email_excerpt": "Dear team...",
    "status": "crm-logged",
}


def _write_store(path, messages):
    data = {"last_poll_time": None, "messages": messages}
    with open(path, "w") as fh:
        json.dump(data, fh)


def _read_entry(path, msg_id):
    data = json.loads(path.read_text())
    return next(m for m in data["messages"] if m["gmail_message_id"] == msg_id)


# ── T010 US1 ──────────────────────────────────────────────────────────────────

def test_notify_deal_happy_path_writes_notified_at(tmp_path):
    """status=crm-logged + NoopAdapter → 'discord-notified', notified_at written."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_DEAL])
    result = notify_deal(_DEAL, NoopAdapter(), str(p))
    assert result == "discord-notified"
    entry = _read_entry(p, "msg-001")
    assert entry["status"] == "discord-notified"
    assert "notified_at" in entry


def test_notify_deal_second_call_returns_skipped_no_adapter_call(tmp_path):
    """Second call with status=discord-notified → 'skipped', adapter.notify not called."""
    p = tmp_path / "store.json"
    already_notified = {**_DEAL, "status": "discord-notified", "notified_at": "2026-07-17T09:00:00Z"}
    _write_store(str(p), [already_notified])
    adapter = MagicMock()
    result = notify_deal(already_notified, adapter, str(p))
    assert result == "skipped"
    adapter.notify.assert_not_called()


def test_notify_deal_fr016_oserror_after_success_returns_discord_notified(tmp_path):
    """FR-016: adapter returns discord-notified but write_notify_outcome raises OSError
    → function returns 'discord-notified' (at-least-once delivery trade-off)."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_DEAL])
    adapter = MagicMock()
    adapter.notify.return_value = "discord-notified"
    with patch("discord_notifier.notifier.write_notify_outcome", side_effect=OSError("disk full")):
        result = notify_deal(_DEAL, adapter, str(p))
    assert result == "discord-notified"


def test_notify_deal_failure_writes_pending_with_error_reason(tmp_path):
    """Adapter returns pending → write_notify_outcome called with notify_error_reason."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_DEAL])
    adapter = MagicMock()
    adapter.notify.return_value = "crm-logged-notify-pending"
    adapter._last_error_reason = "HTTP 503"
    with patch("discord_notifier.notifier.write_notify_outcome") as mock_write:
        notify_deal(_DEAL, adapter, str(p))
    mock_write.assert_called_once()
    _, _, outcome = mock_write.call_args[0]
    assert outcome == "crm-logged-notify-pending"
    kwargs = mock_write.call_args[1]
    assert kwargs.get("notify_error_reason", "")


def test_notify_deal_passes_full_deal_dict_to_adapter(tmp_path):
    """Adapter receives all 9 DealPayload fields — notifier does not strip any."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_DEAL])
    adapter = MagicMock()
    adapter.notify.return_value = "discord-notified"
    notify_deal(_DEAL, adapter, str(p))
    received = adapter.notify.call_args[0][0]
    for field in (
        "gmail_message_id", "sender_email", "sender_name", "subject",
        "received_at", "deal_summary", "deal_category", "confidence_score",
        "raw_email_excerpt",
    ):
        assert field in received, f"field '{field}' was stripped before passing to adapter"


# ── T014 US2: idempotency ─────────────────────────────────────────────────────

def test_idempotency_discord_notified_skips_immediately():
    """Deal already notified → 'skipped' with no adapter call and no state write."""
    deal = {**_DEAL, "status": "discord-notified"}
    adapter = MagicMock()
    with patch("discord_notifier.notifier.write_notify_outcome") as mock_write:
        result = notify_deal(deal, adapter, "/dev/null")
    assert result == "skipped"
    adapter.notify.assert_not_called()
    mock_write.assert_not_called()


def test_idempotency_no_adapter_call_on_skip():
    """Adapter.notify() is never invoked when deal is already discord-notified."""
    deal = {**_DEAL, "status": "discord-notified"}
    adapter = MagicMock()
    notify_deal(deal, adapter, "/dev/null")
    adapter.notify.assert_not_called()


def test_idempotency_state_store_unchanged_on_skip(tmp_path):
    """State store is NOT written when deal is already discord-notified."""
    p = tmp_path / "store.json"
    deal = {**_DEAL, "status": "discord-notified", "notified_at": "2026-07-17T09:00:00Z"}
    _write_store(str(p), [deal])
    before = p.read_text()
    notify_deal(deal, NoopAdapter(), str(p))
    assert p.read_text() == before


# ── T017 US3: failure paths ───────────────────────────────────────────────────

def test_failure_writes_non_empty_notify_error_reason(tmp_path):
    """Pending outcome → notify_error_reason is non-empty string in state store."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_DEAL])
    adapter = MagicMock()
    adapter.notify.return_value = "crm-logged-notify-pending"
    adapter._last_error_reason = "HTTP 429 (retry_after=2.0s)"
    notify_deal(_DEAL, adapter, str(p))
    entry = _read_entry(p, "msg-001")
    assert entry.get("notify_error_reason", "") != ""


def test_fr016_delivery_success_write_failure_returns_notified(tmp_path):
    """FR-016: Discord delivery confirmed but state write raises OSError
    → return value is still 'discord-notified'."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_DEAL])
    adapter = MagicMock()
    adapter.notify.return_value = "discord-notified"
    with patch("discord_notifier.notifier.write_notify_outcome", side_effect=OSError("disk full")):
        result = notify_deal(_DEAL, adapter, str(p))
    assert result == "discord-notified"


def test_notify_error_reason_truncated_to_255_chars(tmp_path):
    """notify_error_reason is capped at 255 chars even when adapter reports a long failure."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_DEAL])
    adapter = MagicMock()
    adapter.notify.return_value = "crm-logged-notify-pending"
    adapter._last_error_reason = "X" * 300
    with patch("discord_notifier.notifier.write_notify_outcome") as mock_write:
        notify_deal(_DEAL, adapter, str(p))
    kwargs = mock_write.call_args[1]
    assert len(kwargs["notify_error_reason"]) <= 255


def test_notified_at_absent_on_pending_transition(tmp_path):
    """notified_at must NOT appear in state store when deal transitions to pending."""
    p = tmp_path / "store.json"
    _write_store(str(p), [_DEAL])
    adapter = MagicMock()
    adapter.notify.return_value = "crm-logged-notify-pending"
    adapter._last_error_reason = "HTTP 500"
    notify_deal(_DEAL, adapter, str(p))
    entry = _read_entry(p, "msg-001")
    assert "notified_at" not in entry
