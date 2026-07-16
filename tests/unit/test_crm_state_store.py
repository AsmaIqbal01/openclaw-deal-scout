"""Unit tests for src/crm_logger/state_store.py."""

import json
import os
import tempfile

import pytest

from crm_logger.state_store import (
    get_new_deals,
    get_pending_deals,
    read_crm_store,
    write_crm_outcome,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_store_file(tmp_path):
    """A state store file with no messages and counter=0."""
    data = {"last_poll_time": "2024-01-01T00:00:00Z", "messages": [], "consecutive_401_cycles": 0}
    p = tmp_path / "processed_ids.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


@pytest.fixture
def mixed_store_file(tmp_path):
    """Store file with one deal_extracted, one crm-pending, one crm-logged message."""
    messages = [
        {
            "gmail_message_id": "msg-new",
            "status": "deal_extracted",
            "subject": "New deal",
            "sender_email": "a@example.com",
            "sender_name": "Alice",
            "received_at": "2024-01-02T10:00:00Z",
            "deal_category": "contract",
            "confidence_score": 0.9,
            "deal_summary": "A deal",
        },
        {
            "gmail_message_id": "msg-pending",
            "status": "crm-pending",
            "subject": "Pending deal",
            "sender_email": "b@example.com",
            "sender_name": "Bob",
            "received_at": "2024-01-02T11:00:00Z",
            "deal_category": "rfp",
            "confidence_score": 0.8,
            "deal_summary": "A pending deal",
        },
        {
            "gmail_message_id": "msg-logged",
            "status": "crm-logged",
            "subject": "Done deal",
            "sender_email": "c@example.com",
            "sender_name": "Carol",
            "received_at": "2024-01-02T12:00:00Z",
            "deal_category": "other",
            "confidence_score": 0.7,
            "deal_summary": "A logged deal",
            "hubspot_deal_id": "hs-123",
        },
    ]
    data = {
        "last_poll_time": "2024-01-02T12:00:00Z",
        "messages": messages,
        "consecutive_401_cycles": 2,
    }
    p = tmp_path / "processed_ids.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# read_crm_store
# ---------------------------------------------------------------------------

def test_read_crm_store_missing_file_returns_empty(tmp_path):
    path = str(tmp_path / "nonexistent.json")
    store = read_crm_store(path)
    assert store.messages == []
    assert store.consecutive_401_cycles == 0
    assert store.last_poll_time is None


def test_read_crm_store_returns_consecutive_401_cycles(mixed_store_file):
    store = read_crm_store(mixed_store_file)
    assert store.consecutive_401_cycles == 2


def test_read_crm_store_defaults_counter_to_0_when_absent(tmp_path):
    data = {"last_poll_time": None, "messages": []}
    p = tmp_path / "processed_ids.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    store = read_crm_store(str(p))
    assert store.consecutive_401_cycles == 0


def test_read_crm_store_loads_all_messages(mixed_store_file):
    store = read_crm_store(mixed_store_file)
    assert len(store.messages) == 3


# ---------------------------------------------------------------------------
# get_pending_deals
# ---------------------------------------------------------------------------

def test_get_pending_deals_filters_correctly(mixed_store_file):
    store = read_crm_store(mixed_store_file)
    pending = get_pending_deals(store)
    assert len(pending) == 1
    assert pending[0]["gmail_message_id"] == "msg-pending"


def test_get_pending_deals_empty_when_none_pending(empty_store_file):
    store = read_crm_store(empty_store_file)
    assert get_pending_deals(store) == []


# ---------------------------------------------------------------------------
# get_new_deals
# ---------------------------------------------------------------------------

def test_get_new_deals_filters_correctly(mixed_store_file):
    store = read_crm_store(mixed_store_file)
    new = get_new_deals(store)
    assert len(new) == 1
    assert new[0]["gmail_message_id"] == "msg-new"


def test_get_new_deals_empty_when_none_extracted(empty_store_file):
    store = read_crm_store(empty_store_file)
    assert get_new_deals(store) == []


# ---------------------------------------------------------------------------
# write_crm_outcome
# ---------------------------------------------------------------------------

def test_write_crm_outcome_updates_outcome_field(mixed_store_file):
    write_crm_outcome(mixed_store_file, "msg-new", "crm-logged", hubspot_deal_id="hs-999")
    store = read_crm_store(mixed_store_file)
    updated = next(m for m in store.messages if m["gmail_message_id"] == "msg-new")
    assert updated["status"] == "crm-logged"
    assert updated["hubspot_deal_id"] == "hs-999"


def test_write_crm_outcome_preserves_other_messages(mixed_store_file):
    write_crm_outcome(mixed_store_file, "msg-new", "crm-pending", error_reason="timeout")
    store = read_crm_store(mixed_store_file)
    pending_msg = next(m for m in store.messages if m["gmail_message_id"] == "msg-pending")
    assert pending_msg["status"] == "crm-pending"  # unchanged


def test_write_crm_outcome_preserves_consecutive_401_cycles(mixed_store_file):
    write_crm_outcome(mixed_store_file, "msg-new", "crm-pending")
    store = read_crm_store(mixed_store_file)
    # merge-write must not reset the 401 counter
    assert store.consecutive_401_cycles == 2
