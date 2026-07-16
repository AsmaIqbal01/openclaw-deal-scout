"""CRM Logger — deal-level write logic.

Implements log_deal() which writes one DealPayload entry to HubSpot and
updates the shared state store accordingly.

FR-014: name split on first space only.
FR-004: dealname truncated to 255 chars (252 + "...").
FR-006: received_at ISO-8601 converted to Unix epoch milliseconds.
"""

import logging
import re
from datetime import datetime
from typing import Literal

import requests

from crm_logger.models import (
    HubSpot401Error,
    HubSpotMissingResourceIdError,
    HubSpotRateLimitError,
    HubSpotResponseError,
)
from crm_logger.state_store import read_crm_store, write_crm_outcome

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Pure helper functions (FR-014, FR-004, FR-006)
# ---------------------------------------------------------------------------

def split_name(sender_name: str | None) -> tuple[str, str]:
    """Split a full name into (firstname, lastname) on the first space.

    >>> split_name("Jane Doe Smith")
    ('Jane', 'Doe Smith')
    >>> split_name("Alice")
    ('Alice', '')
    >>> split_name(None)
    ('', '')
    """
    if not sender_name:
        return ("", "")
    parts = sender_name.split(" ", maxsplit=1)
    return (parts[0], parts[1] if len(parts) > 1 else "")


def truncate_dealname(subject: str) -> str:
    """Truncate deal name to 255 chars; append '...' if trimmed (FR-004).

    >>> len(truncate_dealname("x" * 300))
    255
    >>> truncate_dealname("short")
    'short'
    """
    if len(subject) <= 255:
        return subject
    return subject[:252] + "..."


def to_epoch_ms(iso_str: str) -> int:
    """Convert ISO-8601 string to Unix epoch milliseconds (FR-006).

    >>> to_epoch_ms("2024-01-02T10:00:00Z")
    1704189600000
    """
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# log_deal
# ---------------------------------------------------------------------------

def log_deal(
    payload: dict,
    client: object,
    state_path: str,
) -> Literal["crm-logged", "crm-pending", "skipped"]:
    """Write one deal payload to HubSpot and record the outcome in state store.

    Returns:
        "crm-logged"  — deal successfully written to HubSpot
        "crm-pending" — write failed; entry queued for retry
        "skipped"     — deal already logged (FR-002 idempotency)

    Raises HubSpot401Error without catching it so the orchestrator can
    handle credential suspension at the cycle level.
    """
    gmail_message_id: str = payload["gmail_message_id"]

    # FR-002: idempotency — skip if already logged
    if payload.get("status") == "crm-logged":
        logger.debug("skipping already-logged deal %s", gmail_message_id)
        return "skipped"

    # FR-007: validate sender_email before any network call
    sender_email: str = payload.get("sender_email", "")
    if not _EMAIL_RE.match(sender_email):
        logger.warning(
            "crm-pending: invalid_sender_email for %s (email=%r)",
            gmail_message_id,
            sender_email,
        )
        write_crm_outcome(
            state_path,
            gmail_message_id,
            "crm-pending",
            error_reason="invalid_sender_email",
        )
        return "crm-pending"

    firstname, lastname = split_name(payload.get("sender_name"))
    dealname = truncate_dealname(payload.get("subject", ""))
    received_date_ms = to_epoch_ms(payload["received_at"])

    try:
        contact_id = client.upsert_contact(  # type: ignore[union-attr]
            sender_email,
            firstname,
            lastname,
            msg_id=gmail_message_id,
        )
        deal_id = client.create_deal(  # type: ignore[union-attr]
            dealname=dealname,
            deal_category=payload.get("deal_category", ""),
            confidence_score=float(payload.get("confidence_score", 0.0)),
            deal_summary=payload.get("deal_summary", ""),
            received_date_ms=received_date_ms,
            gmail_message_id=gmail_message_id,
            contact_id=contact_id,
            msg_id=gmail_message_id,
        )
    except HubSpot401Error:
        # Propagate to orchestrator — cycle-level suspension decision
        raise
    except (
        requests.RequestException,
        HubSpotRateLimitError,
        HubSpotResponseError,
        HubSpotMissingResourceIdError,
    ) as exc:
        logger.warning(
            "crm-pending: %s for gmail_message_id=%s — %s: %s",
            type(exc).__name__,
            gmail_message_id,
            type(exc).__name__,
            exc,
        )
        write_crm_outcome(
            state_path,
            gmail_message_id,
            "crm-pending",
            error_reason=str(exc),
        )
        return "crm-pending"

    # FR-013: treat state-store write failure as crm-pending (don't crash)
    try:
        write_crm_outcome(
            state_path,
            gmail_message_id,
            "crm-logged",
            hubspot_deal_id=deal_id,
        )
    except OSError as exc:
        logger.error(
            "state store write failed after CRM success for %s: %s",
            gmail_message_id,
            exc,
        )
        write_crm_outcome(
            state_path,
            gmail_message_id,
            "crm-pending",
            error_reason=f"state_store_write_failed: {exc}",
        )
        return "crm-pending"

    logger.info("crm-logged: deal_id=%s gmail_message_id=%s", deal_id, gmail_message_id)
    return "crm-logged"
