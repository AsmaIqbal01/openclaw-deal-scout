"""Unit tests for src/crm_logger/orchestrator.py."""

import json
from unittest.mock import MagicMock, patch

import pytest

from crm_logger.models import CrmCycleResult, HubSpot401Error
from crm_logger.state_store import read_crm_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_deal(msg_id: str, status: str = "deal_extracted") -> dict:
    return {
        "gmail_message_id": msg_id,
        "status": status,
        "subject": f"Deal {msg_id}",
        "sender_email": f"{msg_id}@example.com",
        "sender_name": "Alice Doe",
        "received_at": "2024-01-02T10:00:00Z",
        "deal_category": "rfp",
        "confidence_score": 0.9,
        "deal_summary": "A deal summary.",
    }


@pytest.fixture
def drain_store_file(tmp_path):
    """2 crm-pending + 1 deal_extracted."""
    messages = [
        {**_make_deal("pending-1"), "status": "crm-pending"},
        {**_make_deal("pending-2"), "status": "crm-pending"},
        _make_deal("new-1"),
    ]
    data = {"last_poll_time": None, "messages": messages, "consecutive_401_cycles": 0}
    p = tmp_path / "store.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


@pytest.fixture
def circuit_store_file(tmp_path):
    """31 deal_extracted entries."""
    messages = [_make_deal(f"deal-{i:02d}") for i in range(1, 32)]
    data = {"last_poll_time": None, "messages": messages, "consecutive_401_cycles": 0}
    p = tmp_path / "store.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


@pytest.fixture
def one_deal_store(tmp_path):
    """Single deal_extracted entry."""
    data = {
        "last_poll_time": None,
        "messages": [_make_deal("msg-001")],
        "consecutive_401_cycles": 0,
    }
    p = tmp_path / "store.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


@pytest.fixture
def suspended_store(tmp_path):
    """State store with consecutive_401_cycles = 3 (suspended)."""
    data = {
        "last_poll_time": None,
        "messages": [_make_deal("msg-001")],
        "consecutive_401_cycles": 3,
    }
    p = tmp_path / "store.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


@pytest.fixture
def counter_at_2_store(tmp_path):
    """State store with consecutive_401_cycles = 2."""
    data = {
        "last_poll_time": None,
        "messages": [_make_deal("msg-001")],
        "consecutive_401_cycles": 2,
    }
    p = tmp_path / "store.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# T027: Drain-first ordering (US4)
# ---------------------------------------------------------------------------

def test_run_crm_cycle_drains_pending_before_new_deals(drain_store_file):
    """crm-pending entries must be processed before deal_extracted entries."""
    from crm_logger.orchestrator import run_crm_cycle

    call_order = []

    def mock_log_deal(payload, client, state_path):
        call_order.append(payload["gmail_message_id"])
        return "crm-logged"

    with patch("crm_logger.orchestrator.log_deal", side_effect=mock_log_deal):
        result = run_crm_cycle(drain_store_file, "test-token")

    assert result.crm_logged == 3
    # The two pending deals must appear before the new deal
    assert call_order[0] in ("pending-1", "pending-2")
    assert call_order[1] in ("pending-1", "pending-2")
    assert call_order[2] == "new-1"


# ---------------------------------------------------------------------------
# T030: Circuit breaker — 31 deals, 90-call limit (US5)
# ---------------------------------------------------------------------------

def test_circuit_breaker_31_deals_writes_30_defers_1(circuit_store_file):
    """Circuit breaker defers the 31st deal when call_count hits 90."""
    from crm_logger.orchestrator import run_crm_cycle

    def mock_log_deal(payload, client, state_path):
        # Simulate 3 API calls per deal by incrementing the internal counter
        client._call_count += 3
        return "crm-logged"

    with patch("crm_logger.orchestrator.log_deal", side_effect=mock_log_deal):
        result = run_crm_cycle(circuit_store_file, "test-token")

    assert result.crm_logged == 30
    assert result.crm_pending == 1

    store = read_crm_store(circuit_store_file)
    pending_msgs = [m for m in store.messages if m.get("status") == "crm-pending"]
    assert len(pending_msgs) == 1
    assert pending_msgs[0].get("error_reason") == "circuit_breaker_deferred"


def test_circuit_breaker_deferred_entry_has_crm_pending_outcome(circuit_store_file):
    """The deferred entry in the state store must have status 'crm-pending'."""
    from crm_logger.orchestrator import run_crm_cycle

    def mock_log_deal(payload, client, state_path):
        client._call_count += 3
        return "crm-logged"

    with patch("crm_logger.orchestrator.log_deal", side_effect=mock_log_deal):
        run_crm_cycle(circuit_store_file, "test-token")

    store = read_crm_store(circuit_store_file)
    deferred = [m for m in store.messages if m.get("status") == "crm-pending"]
    assert deferred[0]["error_reason"] == "circuit_breaker_deferred"


# ---------------------------------------------------------------------------
# T032: 401 cycle counter (US5)
# ---------------------------------------------------------------------------

def test_401_cycle_counter_increments_on_qualifying_cycle(one_deal_store):
    """All-401 cycle: counter increments from 0 to 1."""
    from crm_logger.orchestrator import run_crm_cycle

    with patch("crm_logger.orchestrator.log_deal", side_effect=HubSpot401Error("401")):
        result = run_crm_cycle(one_deal_store, "test-token")

    store = read_crm_store(one_deal_store)
    assert store.consecutive_401_cycles == 1


def test_mixed_cycle_success_resets_counter(counter_at_2_store):
    """At least one success → counter resets to 0."""
    from crm_logger.orchestrator import run_crm_cycle

    with patch("crm_logger.orchestrator.log_deal", return_value="crm-logged"):
        run_crm_cycle(counter_at_2_store, "test-token")

    store = read_crm_store(counter_at_2_store)
    assert store.consecutive_401_cycles == 0


def test_zero_call_cycle_counter_unchanged(tmp_path):
    """No HubSpot calls (all skipped) → counter unchanged."""
    from crm_logger.orchestrator import run_crm_cycle
    from crm_logger.state_store import write_401_counter

    state_path = str(tmp_path / "store.json")
    # Seed a store with no deals (nothing to process) and counter=1
    data = {"last_poll_time": None, "messages": [], "consecutive_401_cycles": 1}
    (tmp_path / "store.json").write_text(json.dumps(data))

    result = run_crm_cycle(state_path, "test-token")

    store = read_crm_store(state_path)
    assert store.consecutive_401_cycles == 1  # unchanged


def test_suspension_fires_at_3_consecutive_401_cycles(suspended_store):
    """Counter ≥ 3 → suspend without processing any deals."""
    from crm_logger.orchestrator import run_crm_cycle

    with patch("crm_logger.orchestrator.log_deal") as mock_log:
        result = run_crm_cycle(suspended_store, "test-token")

    assert result.suspended is True
    mock_log.assert_not_called()


def test_restart_resets_counter_to_0_with_warn_log(suspended_store, caplog):
    """is_startup=True: reset counter and proceed normally."""
    import logging
    from crm_logger.orchestrator import run_crm_cycle

    with patch("crm_logger.orchestrator.log_deal", return_value="crm-logged"):
        with caplog.at_level(logging.WARNING, logger="crm_logger.orchestrator"):
            result = run_crm_cycle(suspended_store, "test-token", is_startup=True)

    assert result.suspended is False
    assert result.crm_logged == 1
    store = read_crm_store(suspended_store)
    assert store.consecutive_401_cycles == 0
    assert any("restarting" in r.message.lower() for r in caplog.records)
