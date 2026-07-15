"""
T026 — Integration tests for check_new_deals_handler().

Unlike unit tests, these use a real on-disk state store and real lock,
mocking only the external services (Gmail API, Gemini API). This validates
idempotency, pre-filter, concurrent-invocation rejection, and crash-recovery
behaviour across multiple handler invocations.
"""
import os
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from gmail_intake.models import (
    ClassificationResponse,
    ProcessedMessage,
    StateStore,
)
from gmail_intake.server import check_new_deals_handler
from gmail_intake.state_store import acquire_lock, append_message

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_CLASSIFICATION_DEAL = ClassificationResponse(
    is_deal=True,
    confidence_score=0.9,
    deal_category="lead",
    deal_summary="A deal summary.",
    raw_email_excerpt="Excerpt.",
)


def _metadata_for(msg: dict) -> dict:
    """Return a well-formed metadata dict keyed to the message id."""
    return {
        "gmail_message_id": msg["id"],
        "sender_email": "vendor@example.com",
        "sender_name": "Vendor Corp",
        "subject": "Business Proposal",
        "received_at": "2026-07-10T12:00:00Z",
    }


def _patches(store_path: str, messages: list[dict]) -> ExitStack:
    """Return an ExitStack with all external services patched, real state store."""
    stack = ExitStack()
    stack.enter_context(
        patch.dict(os.environ, {
            "GMAIL_CREDENTIALS_PATH": "/fake/creds.json",
            "GEMINI_API_KEY": "fake-key",
            "STATE_STORE_PATH": store_path,
        })
    )
    stack.enter_context(patch("gmail_intake.server.build_service"))
    stack.enter_context(patch("gmail_intake.server.poll_inbox", return_value=messages))
    stack.enter_context(patch("gmail_intake.server.extract_body", return_value="email body"))
    stack.enter_context(
        patch("gmail_intake.server.extract_metadata", side_effect=_metadata_for)
    )
    return stack


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


async def test_idempotent_rerun(tmp_path):
    """
    Two consecutive calls on the same 3-message inbox: first extracts 3 deals;
    second sees all 3 already in the state store and returns processed_count=0.
    """
    store_path = str(tmp_path / "state.json")
    messages = [{"id": "msg1"}, {"id": "msg2"}, {"id": "msg3"}]

    with _patches(store_path, messages) as stack:
        stack.enter_context(
            patch("gmail_intake.server.classify", return_value=_CLASSIFICATION_DEAL)
        )
        result1 = await check_new_deals_handler()
        result2 = await check_new_deals_handler()

    assert result1["status"] == "ok"
    assert result1["processed_count"] == 3
    assert len(result1["deals_extracted"]) == 3

    assert result2["status"] == "ok"
    assert result2["processed_count"] == 0
    assert result2["deals_extracted"] == []
    assert result2["skipped_count"] == 0


async def test_already_processed_pre_filter(tmp_path):
    """
    A message already in the state store is never passed to classify.
    Gmail returns [msg-x (seeded), msg-new-1, msg-new-2].
    classify must be called exactly twice — once per new message.
    """
    store_path = str(tmp_path / "state.json")

    seed_store = StateStore(last_poll_time=None)
    append_message(
        store_path, seed_store,
        ProcessedMessage(
            gmail_message_id="msg-x",
            processed_at="2026-07-09T12:00:00+00:00",
            outcome="deal_extracted",
        ),
    )

    messages = [{"id": "msg-x"}, {"id": "msg-new-1"}, {"id": "msg-new-2"}]

    with _patches(store_path, messages) as stack:
        mock_classify = stack.enter_context(
            patch("gmail_intake.server.classify", return_value=_CLASSIFICATION_DEAL)
        )
        result = await check_new_deals_handler()

    assert mock_classify.call_count == 2
    assert result["processed_count"] == 2
    assert len(result["deals_extracted"]) == 2


async def test_concurrent_invocation_rejected(tmp_path):
    """
    A second invocation while the lock is already held returns status='error'
    with error_details='concurrent invocation' immediately, without processing.
    """
    store_path = str(tmp_path / "state.json")

    held_lock = acquire_lock(store_path)
    try:
        with patch.dict(os.environ, {
            "GMAIL_CREDENTIALS_PATH": "/fake/creds.json",
            "GEMINI_API_KEY": "fake-key",
            "STATE_STORE_PATH": store_path,
        }):
            result = await check_new_deals_handler()
    finally:
        held_lock.release()

    assert result["status"] == "error"
    assert result["error_details"] == "concurrent invocation"
    assert result["deals_extracted"] == []


async def test_process_kill_recovery(tmp_path):
    """
    Simulate a process kill mid-run: msg1 and msg2 were persisted to the state
    store, but msg3 was not processed before the kill. On the next invocation
    with the same 3 messages, only msg3 is classified.
    """
    store_path = str(tmp_path / "state.json")

    seed_store = StateStore(last_poll_time=None)
    append_message(
        store_path, seed_store,
        ProcessedMessage(
            gmail_message_id="msg1",
            processed_at="2026-07-10T11:00:00+00:00",
            outcome="deal_extracted",
        ),
    )
    append_message(
        store_path, seed_store,
        ProcessedMessage(
            gmail_message_id="msg2",
            processed_at="2026-07-10T11:01:00+00:00",
            outcome="deal_extracted",
        ),
    )

    messages = [{"id": "msg1"}, {"id": "msg2"}, {"id": "msg3"}]

    with _patches(store_path, messages) as stack:
        mock_classify = stack.enter_context(
            patch("gmail_intake.server.classify", return_value=_CLASSIFICATION_DEAL)
        )
        result = await check_new_deals_handler()

    assert mock_classify.call_count == 1
    assert result["processed_count"] == 1
    assert len(result["deals_extracted"]) == 1
    assert result["deals_extracted"][0]["gmail_message_id"] == "msg3"
