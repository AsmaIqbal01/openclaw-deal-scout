"""Integration tests for email scheduling end-to-end flow — T026."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from email_scheduler.audit_logger import AuditLogger
from email_scheduler.models import EmailEvent, EventType, ScheduledEmail
from email_scheduler.queue_store import EmailQueueStore
from email_scheduler.scheduler import dispatch_pending, schedule_for_deal


# ── Helpers ───────────────────────────────────────────────────────────────────


def _deal(
    gmail_message_id: str = "msg_e2e",
    sender_email: str = "buyer@example.com",
    sender_name: str = "Bob",
    company_name: str = "AcmeCo",
    deal_summary: str = "Order for 100 units",
) -> dict:
    return {
        "gmail_message_id": gmail_message_id,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "company_name": company_name,
        "deal_summary": deal_summary,
    }


def _make_store(tmp_path) -> EmailQueueStore:
    s = EmailQueueStore(tmp_path / "email_queue.json")
    s.load()
    return s


def _make_audit(tmp_path) -> AuditLogger:
    return AuditLogger(tmp_path / "email_audit.log")


def _make_cfg(tmp_path):
    from email_scheduler.config import EmailSchedulerConfig
    return EmailSchedulerConfig(
        gmail_credentials_path="/tmp/creds.json",
        email_from_address="sender@example.com",
        email_queue_path=str(tmp_path / "email_queue.json"),
        email_audit_log_path=str(tmp_path / "email_audit.log"),
        email_template_path=None,
        email_enabled=True,
    )


def _approved_email(
    tmp_path,
    email_id: str | None = None,
    gid: str | None = None,
    retry_count: int = 0,
    retry_after: str | None = None,
) -> ScheduledEmail:
    return ScheduledEmail(
        id=email_id or str(uuid.uuid4()),
        gmail_message_id=gid or ("msg_" + str(uuid.uuid4())[:8]),
        recipient_name="Bob",
        recipient_email="bob@example.com",
        subject="Follow-up",
        body="Hello Bob",
        status="approved",
        proposed_send_at="2026-07-28T09:00:00Z",
        created_at="2026-07-22T09:00:00Z",
        retry_count=retry_count,
        retry_after=retry_after,
    )


@pytest.fixture(autouse=True)
def _reset_singletons():
    import email_scheduler.queue_store as qs_mod
    import email_scheduler.audit_logger as al_mod
    qs_mod._store = None
    al_mod._audit_logger = None
    yield
    qs_mod._store = None
    al_mod._audit_logger = None


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestScheduleToApproveToSend:
    def test_schedule_creates_entry_in_store(self, tmp_path):
        store = _make_store(tmp_path)
        audit = _make_audit(tmp_path)

        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.scheduler._is_discord_notified", return_value=True
            ),
        ):
            result = schedule_for_deal(_deal())

        assert result["status"] == "scheduled"
        emails = store.list_emails()
        assert len(emails) == 1
        assert emails[0].status == "scheduled"

    def test_schedule_writes_scheduled_audit_event(self, tmp_path):
        store = _make_store(tmp_path)
        audit = _make_audit(tmp_path)

        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.scheduler._is_discord_notified", return_value=True
            ),
        ):
            schedule_for_deal(_deal())

        events = audit.get_events()
        assert any(e.event_type == EventType.SCHEDULED.value for e in events)

    def test_approve_via_store_then_dispatch_sends_email(self, tmp_path):
        em = _approved_email(tmp_path)
        store = _make_store(tmp_path, )
        store._emails.append(em)
        audit = _make_audit(tmp_path)
        cfg = _make_cfg(tmp_path)

        mock_service = mock.MagicMock()
        mock_service.users().messages().send().execute.return_value = {"id": "gm_sent"}

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.auth.build_send_service", return_value=mock_service
            ),
            mock.patch("email_scheduler.scheduler.is_business_hours", return_value=True),
        ):
            result = dispatch_pending()

        assert result["dispatched"] == 1
        found = store.get_by_id(em.id)
        assert found.status == "sent"

    def test_dispatch_writes_sent_audit_event(self, tmp_path):
        em = _approved_email(tmp_path)
        store = _make_store(tmp_path)
        store._emails.append(em)
        audit = _make_audit(tmp_path)
        cfg = _make_cfg(tmp_path)

        mock_service = mock.MagicMock()
        mock_service.users().messages().send().execute.return_value = {"id": "gm_ok"}

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.auth.build_send_service", return_value=mock_service
            ),
            mock.patch("email_scheduler.scheduler.is_business_hours", return_value=True),
        ):
            dispatch_pending()

        events = audit.get_events()
        assert any(e.event_type == EventType.SENT.value for e in events)


class TestRetryFlow:
    def test_three_consecutive_failures_reach_failed_status(self, tmp_path):
        em = _approved_email(tmp_path, retry_count=2, retry_after=None)
        store = _make_store(tmp_path)
        store._emails.append(em)
        audit = _make_audit(tmp_path)
        cfg = _make_cfg(tmp_path)

        mock_service = mock.MagicMock()
        mock_service.users().messages().send().execute.side_effect = RuntimeError("down")

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.auth.build_send_service", return_value=mock_service
            ),
            mock.patch("email_scheduler.scheduler.is_business_hours", return_value=True),
        ):
            dispatch_pending()

        found = store.get_by_id(em.id)
        assert found.status == "failed"
        assert found.retry_count == 3

    def test_retry_after_in_future_skips_dispatch(self, tmp_path):
        future = (
            datetime.now(timezone.utc) + timedelta(hours=2)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        em = _approved_email(tmp_path, retry_count=1, retry_after=future)
        store = _make_store(tmp_path)
        store._emails.append(em)
        audit = _make_audit(tmp_path)
        cfg = _make_cfg(tmp_path)

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch("email_scheduler.scheduler.is_business_hours", return_value=True),
        ):
            result = dispatch_pending()

        assert result["skipped"] >= 1
        assert result["dispatched"] == 0


class TestOutsideBusinessHours:
    def test_dispatch_on_weekend_skips_all(self, tmp_path):
        em = _approved_email(tmp_path)
        store = _make_store(tmp_path)
        store._emails.append(em)
        audit = _make_audit(tmp_path)
        cfg = _make_cfg(tmp_path)

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch("email_scheduler.scheduler.is_business_hours", return_value=False),
        ):
            result = dispatch_pending()

        assert result["dispatched"] == 0
        assert result["skipped"] >= 1


class TestStartupRecovery:
    def test_repair_from_audit_fixes_approved_after_crash(self, tmp_path):
        email_id = str(uuid.uuid4())
        em = ScheduledEmail(
            id=email_id,
            gmail_message_id="msg_crash",
            recipient_name="Carol",
            recipient_email="carol@example.com",
            subject="Recovery test",
            body="Body",
            status="approved",
            proposed_send_at="2026-07-28T09:00:00Z",
            created_at="2026-07-22T09:00:00Z",
        )
        store = _make_store(tmp_path)
        store._emails.append(em)

        audit = _make_audit(tmp_path)
        sent_event = EmailEvent(
            event_id=str(uuid.uuid4()),
            email_id=email_id,
            gmail_message_id="msg_crash",
            event_type="sent",
            timestamp="2026-07-22T10:00:00Z",
            actor="system",
        )
        audit.write(sent_event)

        store._repair_from_audit(tmp_path / "email_audit.log", audit)

        repaired = store.get_by_id(email_id)
        assert repaired.status == "sent"
        assert repaired.sent_at == "2026-07-22T10:00:00Z"

        events = audit.get_events()
        assert any(e.event_type == EventType.RECOVERED.value for e in events)
