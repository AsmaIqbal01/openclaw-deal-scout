"""
T024 — Contract tests for check_new_deals_handler().

Verifies the return shape, status semantics, count identity, and DealPayload
field types defined in specs/001-gmail-intake/contracts/tool-contract.md.

All tests mock the full pipeline so they exercise only the contract surface,
not the individual pipeline steps (those are covered by unit tests).
"""
import dataclasses
import os
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from gmail_intake.models import ClassificationResponse, DealPayload, StateStore
from gmail_intake.server import check_new_deals_handler

# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"status", "deals_extracted", "processed_count", "skipped_count", "error_details"}
_VALID_STATUSES = {"ok", "error"}
_VALID_CATEGORIES = {"lead", "partnership_inquiry", "vendor_offer", "rfq", "other"}
_DEAL_PAYLOAD_FIELDS = {f.name for f in dataclasses.fields(DealPayload)}

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_DEAL = DealPayload(
    gmail_message_id="msg1",
    sender_email="vendor@example.com",
    sender_name="Vendor Corp",
    subject="Deal Opportunity",
    received_at="2026-07-10T12:00:00Z",
    deal_summary="A great deal enquiry.",
    deal_category="lead",
    confidence_score=0.9,
    raw_email_excerpt="We have a proposal.",
)

_CLASSIFICATION = ClassificationResponse(
    is_deal=True,
    confidence_score=0.9,
    deal_category="lead",
    deal_summary="A great deal enquiry.",
    raw_email_excerpt="We have a proposal.",
)

_METADATA = {
    "gmail_message_id": "msg1",
    "sender_email": "vendor@example.com",
    "sender_name": "Vendor Corp",
    "subject": "Deal Opportunity",
    "received_at": "2026-07-10T12:00:00Z",
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ok_pipeline():
    """Patch the full pipeline for a successful single-deal run."""
    lock = MagicMock()
    with ExitStack() as stack:
        stack.enter_context(
            patch.dict(os.environ, {"GMAIL_CREDENTIALS_PATH": "/fake/creds.json",
                                    "GEMINI_API_KEY": "fake-key"})
        )
        stack.enter_context(patch("gmail_intake.server.acquire_lock", return_value=lock))
        stack.enter_context(
            patch("gmail_intake.server.read_store",
                  return_value=StateStore(last_poll_time=None))
        )
        stack.enter_context(patch("gmail_intake.server.check_store_size"))
        stack.enter_context(patch("gmail_intake.server.build_service"))
        stack.enter_context(
            patch("gmail_intake.server.poll_inbox", return_value=[{"id": "msg1"}])
        )
        stack.enter_context(
            patch("gmail_intake.server.extract_body", return_value="Email body")
        )
        stack.enter_context(
            patch("gmail_intake.server.extract_metadata", return_value=_METADATA)
        )
        stack.enter_context(
            patch("gmail_intake.server.classify", return_value=_CLASSIFICATION)
        )
        stack.enter_context(
            patch("gmail_intake.server.extract_payload", return_value=_DEAL)
        )
        stack.enter_context(patch("gmail_intake.server.append_message"))
        stack.enter_context(patch("gmail_intake.server.update_poll_time"))
        yield


@pytest.fixture
def empty_inbox_pipeline():
    """Patch the pipeline to simulate an empty Gmail inbox."""
    lock = MagicMock()
    with ExitStack() as stack:
        stack.enter_context(
            patch.dict(os.environ, {"GMAIL_CREDENTIALS_PATH": "/fake/creds.json",
                                    "GEMINI_API_KEY": "fake-key"})
        )
        stack.enter_context(patch("gmail_intake.server.acquire_lock", return_value=lock))
        stack.enter_context(
            patch("gmail_intake.server.read_store",
                  return_value=StateStore(last_poll_time=None))
        )
        stack.enter_context(patch("gmail_intake.server.check_store_size"))
        stack.enter_context(patch("gmail_intake.server.build_service"))
        stack.enter_context(patch("gmail_intake.server.poll_inbox", return_value=[]))
        stack.enter_context(patch("gmail_intake.server.update_poll_time"))
        yield


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


async def test_return_shape_ok(ok_pipeline):
    """Return dict has exactly the 5 keys defined in the tool contract."""
    result = await check_new_deals_handler()
    assert set(result.keys()) == _REQUIRED_KEYS


async def test_status_is_valid_value(ok_pipeline):
    """status is 'ok' or 'error' — no other values are permitted."""
    result = await check_new_deals_handler()
    assert result["status"] in _VALID_STATUSES
    assert result["status"] == "ok"


async def test_deals_extracted_is_list(ok_pipeline):
    """deals_extracted is always a list, never null."""
    result = await check_new_deals_handler()
    assert isinstance(result["deals_extracted"], list)


async def test_count_identity_ok(ok_pipeline):
    """processed_count == len(deals_extracted) + skipped_count (tool-contract.md identity)."""
    result = await check_new_deals_handler()
    assert result["processed_count"] == len(result["deals_extracted"]) + result["skipped_count"]


async def test_deal_payload_all_nine_fields(ok_pipeline):
    """Each item in deals_extracted has exactly the 9 DealPayload fields with correct types."""
    result = await check_new_deals_handler()
    assert len(result["deals_extracted"]) == 1
    deal = result["deals_extracted"][0]

    assert set(deal.keys()) == _DEAL_PAYLOAD_FIELDS
    assert isinstance(deal["gmail_message_id"], str)
    assert isinstance(deal["sender_email"], str)
    assert deal["sender_name"] is None or isinstance(deal["sender_name"], str)
    assert isinstance(deal["subject"], str)
    assert isinstance(deal["received_at"], str)
    assert isinstance(deal["deal_summary"], str)
    assert deal["deal_category"] in _VALID_CATEGORIES
    assert isinstance(deal["confidence_score"], float)
    assert deal["raw_email_excerpt"] is None or isinstance(deal["raw_email_excerpt"], str)


async def test_return_shape_error():
    """Fatal env-var error: return dict still has exactly the 5 keys, status='error'."""
    with patch("gmail_intake.server._get_env",
               side_effect=EnvironmentError("GMAIL_CREDENTIALS_PATH is not set")):
        result = await check_new_deals_handler()
    assert set(result.keys()) == _REQUIRED_KEYS
    assert result["status"] == "error"
    assert isinstance(result["deals_extracted"], list)
    assert result["deals_extracted"] == []
    assert result["processed_count"] == len(result["deals_extracted"]) + result["skipped_count"]


async def test_count_identity_empty_inbox(empty_inbox_pipeline):
    """Count identity holds when inbox is empty."""
    result = await check_new_deals_handler()
    assert result["status"] == "ok"
    assert result["deals_extracted"] == []
    assert result["processed_count"] == len(result["deals_extracted"]) + result["skipped_count"]
