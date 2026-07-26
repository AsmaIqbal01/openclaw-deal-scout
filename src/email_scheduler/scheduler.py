"""
schedule_for_deal(), dispatch_pending(), is_business_hours(), next_business_window().

Threading contract (ADR-0009):
  - schedule_for_deal() and dispatch_pending() run in the pipeline executor thread.
  - All queue writes acquire EmailQueueStore._lock internally.
  - MUST NOT raise — all exceptions are caught and returned/logged.
"""
from __future__ import annotations

import base64
import email.mime.text
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from email_scheduler.models import AuthError, EmailEvent, EventType, ScheduledEmail

logger = logging.getLogger(__name__)

_RETRY_INTERVALS_SECONDS = [60, 120, 240]


# ── Utilities ─────────────────────────────────────────────────────────────────


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_valid_email(value: str | None) -> bool:
    """FR-008 email validation rule."""
    if not value or not isinstance(value, str):
        return False
    parts = value.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    return bool(local) and "." in domain and bool(domain.split(".")[-1])


def _is_present(value: object) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())


def _is_discord_notified(gmail_message_id: str) -> bool:
    """
    Check the pipeline state store to confirm a deal has reached 'discord-notified' status.
    Returns False (conservative) if the state store cannot be read.
    """
    state_path = Path(os.environ.get("STATE_STORE_PATH", "processed_ids.json"))
    try:
        with open(state_path, encoding="utf-8") as fh:
            data = json.load(fh)
        for msg in data.get("messages", []):
            if msg.get("gmail_message_id") == gmail_message_id:
                return msg.get("status") == "discord-notified"
    except (OSError, json.JSONDecodeError):
        pass
    return False


# ── Business-hours gate (US3, ADR-0008, research R-002) ───────────────────────


def is_business_hours(dt_utc: datetime) -> bool:
    """
    Return True if dt_utc falls within Mon–Fri 09:00–17:00 Europe/London (DST-aware).
    Falls back to UTC on ZoneInfoNotFoundError.
    """
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore[import]
        try:
            tz = ZoneInfo("Europe/London")
        except ZoneInfoNotFoundError:
            logger.warning(
                "zoneinfo_unavailable: Europe/London not found — falling back to UTC "
                "for business-hours evaluation"
            )
            tz = timezone.utc
        local = dt_utc.astimezone(tz)
    except ImportError:
        logger.warning(
            "zoneinfo_unavailable: zoneinfo module not available — falling back to UTC"
        )
        local = dt_utc.astimezone(timezone.utc)

    if local.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return 9 <= local.hour < 17


def next_business_window(dt_utc: datetime) -> datetime:
    """
    Return the next Mon–Fri 09:00 Europe/London as a UTC datetime.
    Returns dt_utc unchanged if already within business hours.
    """
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore[import]
        try:
            tz = ZoneInfo("Europe/London")
        except ZoneInfoNotFoundError:
            tz = timezone.utc
    except ImportError:
        tz = timezone.utc

    local = dt_utc.astimezone(tz)

    # Already in window
    if local.weekday() < 5 and 9 <= local.hour < 17:
        return dt_utc

    # Advance to next eligible 09:00
    candidate = local.replace(hour=9, minute=0, second=0, microsecond=0)
    if local.hour >= 17 or local.weekday() >= 5:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)

    return candidate.astimezone(timezone.utc)


# ── US1: Auto-schedule on deal detection ─────────────────────────────────────


def schedule_for_deal(deal_payload: dict) -> dict:
    """
    Schedule a follow-up email for a deal. MUST NOT raise.

    Returns dict with 'status' one of: "scheduled", "skipped", "error".
    """
    try:
        from email_scheduler.audit_logger import get_audit_logger
        from email_scheduler.queue_store import get_store
        from email_scheduler.template import render_email

        audit = get_audit_logger()
        store = get_store()

        gmail_message_id = deal_payload.get("gmail_message_id")
        if not _is_present(gmail_message_id):
            audit.write(EmailEvent(
                event_id=str(uuid.uuid4()),
                email_id=None,
                gmail_message_id=None,
                event_type=EventType.SCHEDULER_ERROR.value,
                timestamp=_utcnow_iso(),
                actor="system",
                error_detail="missing_gmail_message_id",
            ))
            return {"status": "error", "reason": "missing_gmail_message_id"}

        sender_email = deal_payload.get("sender_email")
        if not _is_valid_email(sender_email):
            audit.write(EmailEvent(
                event_id=str(uuid.uuid4()),
                email_id=None,
                gmail_message_id=gmail_message_id,
                event_type=EventType.NO_RECIPIENT.value,
                timestamp=_utcnow_iso(),
                actor="system",
            ))
            return {"status": "skipped", "reason": "no_recipient"}

        if not _is_discord_notified(gmail_message_id):
            return {"status": "skipped", "reason": "not_discord_notified"}

        now = datetime.now(timezone.utc)
        subject, body = render_email(deal_payload)
        email_id = str(uuid.uuid4())
        proposed_send_at = next_business_window(now).strftime("%Y-%m-%dT%H:%M:%SZ")

        email = ScheduledEmail(
            id=email_id,
            gmail_message_id=gmail_message_id,
            recipient_name=deal_payload.get("sender_name") or None,
            recipient_email=sender_email,
            subject=subject,
            body=body,
            status="scheduled",
            proposed_send_at=proposed_send_at,
            created_at=_utcnow_iso(),
        )

        result, _ = store.create(email)

        if result == "skipped":
            audit.write(EmailEvent(
                event_id=str(uuid.uuid4()),
                email_id=None,
                gmail_message_id=gmail_message_id,
                event_type=EventType.DUPLICATE.value,
                timestamp=_utcnow_iso(),
                actor="system",
                recipient_email=sender_email,
            ))
            return {"status": "skipped", "reason": "duplicate"}

        audit.write(EmailEvent(
            event_id=str(uuid.uuid4()),
            email_id=email_id,
            gmail_message_id=gmail_message_id,
            event_type=EventType.SCHEDULED.value,
            timestamp=_utcnow_iso(),
            actor="system",
            recipient_email=sender_email,
        ))
        return {"status": "scheduled", "email_id": email_id}

    except SystemExit:
        logger.warning(
            "schedule_for_deal: email_scheduler config incomplete "
            "(GMAIL_CREDENTIALS_PATH or EMAIL_FROM_ADDRESS missing) — skipping"
        )
        return {"status": "skipped", "reason": "config_incomplete"}
    except Exception as exc:
        logger.exception("schedule_for_deal: unhandled exception")
        try:
            from email_scheduler.audit_logger import get_audit_logger
            get_audit_logger().write(EmailEvent(
                event_id=str(uuid.uuid4()),
                email_id=None,
                gmail_message_id=deal_payload.get("gmail_message_id"),
                event_type=EventType.SCHEDULER_ERROR.value,
                timestamp=_utcnow_iso(),
                actor="system",
                error_detail=str(exc),
            ))
        except Exception:
            pass
        return {"status": "error", "reason": str(exc)}


# ── US3: Smart dispatch with business-hours gate and retry ────────────────────


def _build_raw_message(from_address: str, to_address: str, subject: str, body: str) -> str:
    """Build a base64url-encoded RFC 2822 message for the Gmail API."""
    msg = email.mime.text.MIMEText(body, _charset="utf-8")
    msg["to"] = to_address
    msg["from"] = from_address
    msg["subject"] = subject
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def dispatch_pending() -> dict:
    """
    Dispatch all approved emails that are eligible for sending this cycle.
    MUST NOT raise. Returns {dispatched, skipped, failed}.

    Eligibility: is_business_hours(now) AND (retry_after is None OR retry_after <= now).
    """
    dispatched = 0
    skipped = 0
    failed = 0

    try:
        from email_scheduler.audit_logger import get_audit_logger
        from email_scheduler.auth import build_send_service
        from email_scheduler.config import load_email_config
        from email_scheduler.queue_store import get_store

        cfg = load_email_config()
        store = get_store()
        audit = get_audit_logger()

        if not cfg.email_enabled:
            logger.info("dispatch_pending: EMAIL_ENABLED=false — dispatch skipped this cycle")
            return {"dispatched": 0, "skipped": 0, "failed": 0}

        now = datetime.now(timezone.utc)
        approved = store.list_emails(status_filter="approved")

        for em in approved:
            # Business hours gate
            if not is_business_hours(now):
                skipped += 1
                continue

            # Retry-after gate
            if em.retry_after is not None:
                try:
                    retry_dt = datetime.fromisoformat(em.retry_after.replace("Z", "+00:00"))
                    if now < retry_dt:
                        skipped += 1
                        continue
                except ValueError:
                    pass  # malformed retry_after — attempt dispatch anyway

            # Attempt Gmail API send (no lock held during network call)
            try:
                service = build_send_service(cfg.gmail_credentials_path)
                raw = _build_raw_message(
                    cfg.email_from_address,
                    em.recipient_email,
                    em.subject,
                    em.body,
                )
                service.users().messages().send(
                    userId="me", body={"raw": raw}
                ).execute()

                # Success
                sent_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                store.mark_sent(em.id, sent_at)
                audit.write(EmailEvent(
                    event_id=str(uuid.uuid4()),
                    email_id=em.id,
                    gmail_message_id=em.gmail_message_id,
                    event_type=EventType.SENT.value,
                    timestamp=sent_at,
                    actor="system",
                    recipient_email=em.recipient_email,
                ))
                dispatched += 1

            except (AuthError, Exception) as exc:
                # Failure — increment retry counter
                new_retry_count = em.retry_count + 1
                failed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                retry_after: str | None = None
                if new_retry_count < 3:
                    interval = _RETRY_INTERVALS_SECONDS[new_retry_count - 1]
                    retry_after = (
                        datetime.now(timezone.utc) + timedelta(seconds=interval)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")

                store.mark_retry(em.id, new_retry_count, failed_at, retry_after, str(exc))
                audit.write(EmailEvent(
                    event_id=str(uuid.uuid4()),
                    email_id=em.id,
                    gmail_message_id=em.gmail_message_id,
                    event_type=EventType.FAILED.value,
                    timestamp=failed_at,
                    actor="system",
                    recipient_email=em.recipient_email,
                    error_detail=str(exc),
                    retry_count=new_retry_count,
                ))

                if new_retry_count >= 3:
                    logger.warning(
                        "[WARN] email %s exhausted 3 retries for %s — final failure: %s",
                        em.id,
                        em.recipient_email,
                        exc,
                    )

                failed += 1

    except SystemExit:
        logger.warning(
            "dispatch_pending: email_scheduler config incomplete "
            "(GMAIL_CREDENTIALS_PATH or EMAIL_FROM_ADDRESS missing) — skipping dispatch"
        )
    except Exception as exc:
        logger.exception("dispatch_pending: unhandled exception — returning partial counts")
        try:
            from email_scheduler.audit_logger import get_audit_logger
            get_audit_logger().write(EmailEvent(
                event_id=str(uuid.uuid4()),
                email_id=None,
                gmail_message_id=None,
                event_type=EventType.SCHEDULER_ERROR.value,
                timestamp=_utcnow_iso(),
                actor="system",
                error_detail=f"dispatch_pending unhandled: {exc}",
            ))
        except Exception:
            pass

    return {"dispatched": dispatched, "skipped": skipped, "failed": failed}
