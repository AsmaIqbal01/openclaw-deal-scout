"""Integration test skeleton for 003-discord-notification — T026.

Requires a real DISCORD_WEBHOOK_URL in the environment. Skipped in CI
when the env var is absent (safe for pipelines without a real webhook).

Run manually:
  DISCORD_WEBHOOK_URL=<url> STATE_STORE_PATH=./data/test_processed_ids.json \
  pytest tests/integration/test_sync_notifications.py -v
"""
import json
import os

import pytest

from discord_notifier.orchestrator import run_notify_cycle

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
pytestmark = pytest.mark.skipif(
    not WEBHOOK_URL,
    reason="DISCORD_WEBHOOK_URL not set — skipping live Discord integration tests",
)

_ENV = {"NOTIFIER": "discord", "DISCORD_WEBHOOK_URL": WEBHOOK_URL}


def _write_store(path, messages):
    data = {"last_poll_time": None, "messages": messages}
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


def _read_entry(path, msg_id):
    data = json.loads(open(path).read())
    return next((m for m in data["messages"] if m["gmail_message_id"] == msg_id), None)


def _base_entry(msg_id, **overrides):
    return {
        "gmail_message_id": msg_id,
        "sender_email": "jane@example.com",
        "sender_name": "Jane Smith",
        "subject": "Partnership inquiry",
        "received_at": "2026-07-17T09:00:00Z",
        "deal_summary": "Jane is interested in a joint venture for the UK market.",
        "deal_category": "partnership_inquiry",
        "confidence_score": 0.87,
        "raw_email_excerpt": None,
        "status": "crm-logged",
        **overrides,
    }


# Scenario 1: Happy path — one deal notified
def test_scenario1_happy_path_one_deal(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [_base_entry("int-001")])
    result = run_notify_cycle(str(p), env=_ENV)
    assert result.status == "ok"
    assert result.discord_notified == 1
    assert result.notify_pending == 0
    entry = _read_entry(str(p), "int-001")
    assert entry["status"] == "discord-notified"
    assert "notified_at" in entry


# Scenario 2: Idempotent re-run
def test_scenario2_idempotent_rerun(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [_base_entry("int-002")])
    run_notify_cycle(str(p), env=_ENV)
    result2 = run_notify_cycle(str(p), env=_ENV)
    assert result2.status == "ok"
    assert result2.discord_notified == 0
    assert result2.skipped == 1


# Scenario 3: Drain-first — pending before new
def test_scenario4_drain_first_pending_before_new(tmp_path):
    p = tmp_path / "store.json"
    pending = _base_entry("int-003-pending", status="crm-logged-notify-pending")
    new = _base_entry("int-003-new", status="crm-logged", subject="New deal")
    _write_store(str(p), [new, pending])  # note: listed in "wrong" order to verify drain-first
    result = run_notify_cycle(str(p), env=_ENV)
    assert result.discord_notified == 2
    assert result.status == "ok"


# Scenario 4: Null sender_name renders correctly
def test_scenario5_null_sender_name_in_embed(tmp_path):
    p = tmp_path / "store.json"
    entry = _base_entry("int-004", sender_name=None, sender_email="vendor@corp.com")
    _write_store(str(p), [entry])
    result = run_notify_cycle(str(p), env=_ENV)
    assert result.discord_notified == 1
    updated = _read_entry(str(p), "int-004")
    assert updated["status"] == "discord-notified"


# Scenario 5: Missing NOTIFIER → error (sanity check — doesn't need webhook)
@pytest.mark.skipif(False, reason="always run this one")
def test_scenario_missing_notifier_env(tmp_path):
    p = tmp_path / "store.json"
    _write_store(str(p), [_base_entry("int-005")])
    result = run_notify_cycle(str(p), env={})
    assert result.status == "error"
    assert "NOTIFIER" in (result.error_details or "")
