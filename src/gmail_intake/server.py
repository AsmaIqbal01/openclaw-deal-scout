import dataclasses
import logging
import os
from datetime import datetime, timezone

from fastmcp import FastMCP

from gmail_intake.classifier import classify
from gmail_intake.extractor import extract_body, extract_metadata, extract_payload
from gmail_intake.gmail_client import build_service, poll_inbox
from gmail_intake.models import (
    AuthError,
    ClassificationError,
    ClassificationRequest,
    ConcurrentInvocationError,
    InvalidMetadataError,
    ProcessedMessage,
    RateLimitExhaustedError,
    SchemaValidationError,
    StateStoreReadError,
)
from gmail_intake.state_store import (
    acquire_lock,
    append_message,
    check_store_size,
    read_store,
    update_poll_time,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("gmail-intake")

_BODY_EXCERPT_CAP = 8000


def _get_env() -> dict:
    """Read all runtime env vars at call time. Raises EnvironmentError for missing required vars."""
    credentials_path = os.environ.get("GMAIL_CREDENTIALS_PATH")
    if not credentials_path:
        raise EnvironmentError("GMAIL_CREDENTIALS_PATH is not set")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set")
    state_store_path = os.environ.get("STATE_STORE_PATH") or "./data/processed_ids.json"
    max_messages = int(os.environ.get("MAX_MESSAGES_PER_POLL") or "50")
    return {
        "credentials_path": credentials_path,
        "api_key": api_key,
        "state_store_path": state_store_path,
        "max_messages": max_messages,
    }


def _empty_result(error_details: str | None = None, processed: int = 0, skipped: int = 0) -> dict:
    return {
        "status": "error" if error_details else "ok",
        "deals_extracted": [],
        "processed_count": processed,
        "skipped_count": skipped,
        "error_details": error_details,
    }


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def check_new_deals_handler() -> dict:
    logger.debug("poll cycle start")
    try:
        env = _get_env()
    except EnvironmentError as exc:
        return _empty_result(str(exc))

    state_store_path = env["state_store_path"]

    try:
        lock = acquire_lock(state_store_path)
    except ConcurrentInvocationError:
        return _empty_result("concurrent invocation")

    try:
        try:
            store = read_store(state_store_path)
        except StateStoreReadError as exc:
            return _empty_result(f"State store unreadable: {exc}")

        check_store_size(state_store_path)
        already_processed = {m.gmail_message_id for m in store.messages}

        try:
            service = build_service(env["credentials_path"])
        except AuthError as exc:
            return _empty_result(str(exc))

        try:
            messages = poll_inbox(service, store.last_poll_time, env["max_messages"])
        except Exception as exc:
            return _empty_result(f"Network failure mid-poll: {exc}")

        logger.info("check_new_deals invoked: %d messages fetched", len(messages))
        if not messages:
            logger.info("inbox empty")

        deals_extracted: list[dict] = []
        processed_count = 0
        skipped_count = 0

        for msg in messages:
            msg_id = msg.get("id")
            if msg_id in already_processed:
                continue
            processed_count += 1

            try:
                body = extract_body(msg)
                if not body:
                    logger.info("body absent for message %s", msg_id)
                    append_message(
                        state_store_path,
                        store,
                        ProcessedMessage(
                            gmail_message_id=msg_id,
                            processed_at=_utcnow_iso(),
                            outcome="body_absent",
                        ),
                    )
                    skipped_count += 1
                    continue

                try:
                    metadata = extract_metadata(msg)
                except InvalidMetadataError:
                    append_message(
                        state_store_path,
                        store,
                        ProcessedMessage(
                            gmail_message_id=msg_id,
                            processed_at=_utcnow_iso(),
                            outcome="invalid_metadata",
                        ),
                    )
                    skipped_count += 1
                    continue

                request = ClassificationRequest(
                    subject=metadata["subject"],
                    sender_email=metadata["sender_email"],
                    sender_name=metadata["sender_name"],
                    body_excerpt=body[:_BODY_EXCERPT_CAP],
                )

                try:
                    classification = classify(request, env["api_key"])
                except RateLimitExhaustedError:
                    append_message(
                        state_store_path,
                        store,
                        ProcessedMessage(
                            gmail_message_id=msg_id,
                            processed_at=_utcnow_iso(),
                            outcome="rate_limited",
                        ),
                    )
                    skipped_count += 1
                    continue
                except ClassificationError:
                    append_message(
                        state_store_path,
                        store,
                        ProcessedMessage(
                            gmail_message_id=msg_id,
                            processed_at=_utcnow_iso(),
                            outcome="classification_error",
                        ),
                    )
                    skipped_count += 1
                    continue

                if not classification.is_deal or classification.confidence_score < 0.5:
                    logger.info("deal classified as not_a_deal: %s", msg_id)
                    append_message(
                        state_store_path,
                        store,
                        ProcessedMessage(
                            gmail_message_id=msg_id,
                            processed_at=_utcnow_iso(),
                            outcome="not_a_deal",
                        ),
                    )
                    skipped_count += 1
                    continue

                try:
                    payload = extract_payload(metadata, classification)
                except SchemaValidationError:
                    append_message(
                        state_store_path,
                        store,
                        ProcessedMessage(
                            gmail_message_id=msg_id,
                            processed_at=_utcnow_iso(),
                            outcome="schema_error",
                        ),
                    )
                    skipped_count += 1
                    continue

                deal_dict = dataclasses.asdict(payload)
                state_store_dict = {**deal_dict, "status": "deal_extracted"}
                append_message(
                    state_store_path,
                    store,
                    ProcessedMessage(
                        gmail_message_id=msg_id,
                        processed_at=_utcnow_iso(),
                        outcome="deal_extracted",
                    ),
                    extra_fields=state_store_dict,
                )
                deals_extracted.append(deal_dict)

            except Exception:
                logger.exception("unhandled exception processing message %s", msg_id)
                append_message(
                    state_store_path,
                    store,
                    ProcessedMessage(
                        gmail_message_id=msg_id,
                        processed_at=_utcnow_iso(),
                        outcome="classification_error",
                    ),
                )
                skipped_count += 1
                continue

        update_poll_time(state_store_path, store, _utcnow_iso())

        return {
            "status": "ok",
            "deals_extracted": deals_extracted,
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "error_details": None,
        }
    finally:
        lock.release()
        logger.debug("poll cycle end")


@mcp.tool()
async def check_new_deals() -> dict:
    """
    Poll the operator's Gmail inbox for new business deal emails.
    Returns structured DealPayload records for confirmed deals.
    No parameters required — all config is via environment variables.
    """
    return await check_new_deals_handler()


if __name__ == "__main__":
    mcp.run()
