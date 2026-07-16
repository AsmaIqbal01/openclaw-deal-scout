"""Unit tests for src/crm_logger/log_deal.py."""

import json
import pytest
from unittest.mock import MagicMock, patch

from crm_logger.log_deal import split_name, truncate_dealname, to_epoch_ms
from crm_logger.models import HubSpot401Error, HubSpotResponseError


# ---------------------------------------------------------------------------
# split_name (T008 / FR-014)
# ---------------------------------------------------------------------------

def test_split_name_two_words():
    assert split_name("Jane Doe") == ("Jane", "Doe")


def test_split_name_three_words_splits_on_first_space():
    assert split_name("Jane Doe Smith") == ("Jane", "Doe Smith")


def test_split_name_single_word():
    assert split_name("Alice") == ("Alice", "")


def test_split_name_none_returns_empty_strings():
    assert split_name(None) == ("", "")


def test_split_name_empty_string_returns_empty_strings():
    assert split_name("") == ("", "")


# ---------------------------------------------------------------------------
# truncate_dealname (T008 / FR-004)
# ---------------------------------------------------------------------------

def test_truncate_dealname_short_returns_unchanged():
    assert truncate_dealname("short subject") == "short subject"


def test_truncate_dealname_exactly_255_returns_unchanged():
    subject = "x" * 255
    assert truncate_dealname(subject) == subject


def test_truncate_dealname_256_chars_truncated_to_255():
    subject = "x" * 256
    result = truncate_dealname(subject)
    assert len(result) == 255
    assert result.endswith("...")


def test_truncate_dealname_300_chars_is_252_plus_ellipsis():
    subject = "a" * 300
    result = truncate_dealname(subject)
    assert len(result) == 255
    assert result == "a" * 252 + "..."


# ---------------------------------------------------------------------------
# to_epoch_ms (FR-006)
# ---------------------------------------------------------------------------

def test_to_epoch_ms_utc_z_suffix():
    result = to_epoch_ms("2024-01-02T10:00:00Z")
    assert result == 1704189600000


def test_to_epoch_ms_utc_plus00():
    result = to_epoch_ms("2024-01-02T10:00:00+00:00")
    assert result == 1704189600000


def test_to_epoch_ms_returns_int():
    result = to_epoch_ms("2024-01-02T10:00:00Z")
    assert isinstance(result, int)


# ---------------------------------------------------------------------------
# log_deal — happy path (T010 / US1)
# ---------------------------------------------------------------------------

def _make_payload(gmail_message_id: str = "msg-001", status: str = "deal_extracted") -> dict:
    return {
        "gmail_message_id": gmail_message_id,
        "status": status,
        "subject": "Acme Corp RFP response",
        "sender_email": "alice@acme.com",
        "sender_name": "Alice Doe",
        "received_at": "2024-01-02T10:00:00Z",
        "deal_category": "rfp",
        "confidence_score": 0.92,
        "deal_summary": "Acme wants a proposal.",
    }


@pytest.fixture
def state_file_with_deal(tmp_path):
    payload = _make_payload()
    data = {
        "last_poll_time": "2024-01-02T10:00:00Z",
        "messages": [payload],
        "consecutive_401_cycles": 0,
    }
    p = tmp_path / "processed_ids.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


@pytest.fixture
def state_file_already_logged(tmp_path):
    payload = _make_payload(status="crm-logged")
    payload["hubspot_deal_id"] = "hs-existing"
    data = {
        "last_poll_time": "2024-01-02T10:00:00Z",
        "messages": [payload],
        "consecutive_401_cycles": 0,
    }
    p = tmp_path / "processed_ids.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def _make_mock_client(contact_id: str = "c-1", deal_id: str = "d-1") -> MagicMock:
    client = MagicMock()
    client.upsert_contact.return_value = contact_id
    client.create_deal.return_value = deal_id
    return client


def test_log_deal_creates_contact_and_deal_returns_crm_logged(state_file_with_deal):
    from crm_logger.log_deal import log_deal
    from crm_logger.state_store import read_crm_store

    client = _make_mock_client()
    payload = _make_payload()

    result = log_deal(payload, client, state_file_with_deal)

    assert result == "crm-logged"
    client.upsert_contact.assert_called_once()
    client.create_deal.assert_called_once()

    store = read_crm_store(state_file_with_deal)
    msg = next(m for m in store.messages if m["gmail_message_id"] == "msg-001")
    assert msg["status"] == "crm-logged"
    assert msg.get("hubspot_deal_id") == "d-1"


def test_log_deal_skips_deal_already_crm_logged(state_file_already_logged):
    from crm_logger.log_deal import log_deal

    client = _make_mock_client()
    payload = _make_payload(status="crm-logged")
    payload["hubspot_deal_id"] = "hs-existing"

    result = log_deal(payload, client, state_file_already_logged)

    assert result == "skipped"
    client.upsert_contact.assert_not_called()
    client.create_deal.assert_not_called()


# ---------------------------------------------------------------------------
# log_deal — error paths (T018/T019 / US2)
# ---------------------------------------------------------------------------

def test_log_deal_connection_error_returns_crm_pending(state_file_with_deal):
    from crm_logger.log_deal import log_deal
    from crm_logger.state_store import read_crm_store
    import requests

    client = _make_mock_client()
    client.upsert_contact.side_effect = requests.ConnectionError("timeout")

    result = log_deal(_make_payload(), client, state_file_with_deal)

    assert result == "crm-pending"
    store = read_crm_store(state_file_with_deal)
    msg = next(m for m in store.messages if m["gmail_message_id"] == "msg-001")
    assert msg["status"] == "crm-pending"


def test_log_deal_4xx_returns_crm_pending(state_file_with_deal):
    from crm_logger.log_deal import log_deal

    client = _make_mock_client()
    client.upsert_contact.side_effect = HubSpotResponseError(422, "Unprocessable entity")

    result = log_deal(_make_payload(), client, state_file_with_deal)
    assert result == "crm-pending"


def test_log_deal_missing_resource_id_returns_crm_pending(state_file_with_deal):
    from crm_logger.log_deal import log_deal
    from crm_logger.models import HubSpotMissingResourceIdError

    client = _make_mock_client()
    client.create_deal.side_effect = HubSpotMissingResourceIdError("no id in response")

    result = log_deal(_make_payload(), client, state_file_with_deal)
    assert result == "crm-pending"


def test_log_deal_invalid_sender_email_returns_crm_pending(state_file_with_deal):
    from crm_logger.log_deal import log_deal
    from crm_logger.state_store import read_crm_store

    client = _make_mock_client()
    bad_payload = _make_payload()
    bad_payload["sender_email"] = "not-an-email"

    result = log_deal(bad_payload, client, state_file_with_deal)
    assert result == "crm-pending"
    client.upsert_contact.assert_not_called()


def test_log_deal_401_propagates_as_hubspot_401_error(state_file_with_deal):
    from crm_logger.log_deal import log_deal

    client = _make_mock_client()
    client.upsert_contact.side_effect = HubSpot401Error("401 on POST /contacts")

    with pytest.raises(HubSpot401Error):
        log_deal(_make_payload(), client, state_file_with_deal)


# ---------------------------------------------------------------------------
# T033: FR-015 — 9 payload fields persisted in crm-pending entry (US5)
# ---------------------------------------------------------------------------

def test_fr015_9_fields_in_crm_pending_entry_after_write_failure(state_file_with_deal):
    """All 9 DealPayload fields are present in the crm-pending state entry."""
    from crm_logger.log_deal import log_deal
    from crm_logger.state_store import read_crm_store
    import requests

    client = _make_mock_client()
    client.upsert_contact.side_effect = requests.ConnectionError("timeout")

    payload = _make_payload()
    result = log_deal(payload, client, state_file_with_deal)
    assert result == "crm-pending"

    store = read_crm_store(state_file_with_deal)
    entry = next(m for m in store.messages if m["gmail_message_id"] == "msg-001")

    for field in (
        "gmail_message_id", "subject", "sender_email", "sender_name",
        "received_at", "deal_category", "confidence_score", "deal_summary", "status",
    ):
        assert field in entry, f"Missing field: {field}"

    assert entry["status"] == "crm-pending"


def test_fr015_orchestrator_reconstructs_dealpayload_from_state_store(tmp_path):
    """Orchestrator can retry a crm-pending deal from stored fields alone."""
    from crm_logger.orchestrator import run_crm_cycle

    # Seed a crm-pending entry with all 9 payload fields
    messages = [
        {
            "gmail_message_id": "retry-001",
            "status": "crm-pending",
            "subject": "RFP response needed",
            "sender_email": "bob@example.com",
            "sender_name": "Bob Smith",
            "received_at": "2024-01-02T10:00:00Z",
            "deal_category": "rfp",
            "confidence_score": 0.88,
            "deal_summary": "Bob wants a proposal.",
            "error_reason": "timeout",
        }
    ]
    data = {"last_poll_time": None, "messages": messages, "consecutive_401_cycles": 0}
    state_path = str(tmp_path / "store.json")
    (tmp_path / "store.json").write_text(json.dumps(data))

    seen_payloads = []

    def capture_log_deal(payload, client, sp):
        seen_payloads.append(dict(payload))
        return "crm-logged"

    with patch("crm_logger.orchestrator.log_deal", side_effect=capture_log_deal):
        result = run_crm_cycle(state_path, "test-token")

    assert result.crm_logged == 1
    assert len(seen_payloads) == 1
    p = seen_payloads[0]
    # All 9 fields must be present in the payload passed to log_deal
    for field in (
        "gmail_message_id", "subject", "sender_email", "sender_name",
        "received_at", "deal_category", "confidence_score", "deal_summary", "status",
    ):
        assert field in p, f"Missing field: {field}"
