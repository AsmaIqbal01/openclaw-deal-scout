"""Unit tests for email_scheduler.scheduler — T013 (schedule_for_deal) + T025 (dispatch/hours)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from email_scheduler.models import EmailEvent, EventType, ScheduledEmail
from email_scheduler.queue_store import EmailQueueStore
from email_scheduler.scheduler import (
    dispatch_pending,
    is_business_hours,
    next_business_window,
    schedule_for_deal,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_store(tmp_path, emails=None):
    s = EmailQueueStore(tmp_path / "q.json")
    s.load()
    if emails:
        for em in emails:
            s._emails.append(em)
        s._write_locked()
    return s


def _make_audit(tmp_path):
    from email_scheduler.audit_logger import AuditLogger
    return AuditLogger(tmp_path / "audit.log")


def _approved_email(**kwargs) -> ScheduledEmail:
    defaults = dict(
        id=str(uuid.uuid4()),
        gmail_message_id="msg_" + str(uuid.uuid4())[:8],
        recipient_name="Bob",
        recipient_email="bob@example.com",
        subject="Test",
        body="Body",
        status="approved",
        proposed_send_at="2026-07-28T09:00:00Z",
        created_at="2026-07-22T09:00:00Z",
        retry_count=0,
        retry_after=None,
    )
    defaults.update(kwargs)
    return ScheduledEmail(**defaults)


def _deal(
    gmail_message_id="msg_001",
    sender_email="buyer@example.com",
    sender_name="Carol",
    company_name="TestCo",
    deal_summary="Wants 50 units",
):
    return {
        "gmail_message_id": gmail_message_id,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "company_name": company_name,
        "deal_summary": deal_summary,
    }


# ── T013: schedule_for_deal ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Ensure queue_store and audit_logger singletons are reset between tests."""
    import email_scheduler.queue_store as qs_mod
    import email_scheduler.audit_logger as al_mod
    qs_mod._store = None
    al_mod._audit_logger = None
    yield
    qs_mod._store = None
    al_mod._audit_logger = None


class TestScheduleForDeal:
    def test_valid_discord_notified_deal_returns_scheduled(self, tmp_path):
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
        assert "email_id" in result

    def test_missing_gmail_message_id_returns_error(self, tmp_path):
        store = _make_store(tmp_path)
        audit = _make_audit(tmp_path)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
        ):
            result = schedule_for_deal({**_deal(), "gmail_message_id": None})
        assert result["status"] == "error"
        assert result["reason"] == "missing_gmail_message_id"

    def test_missing_gmail_message_id_never_raises(self, tmp_path):
        store = _make_store(tmp_path)
        audit = _make_audit(tmp_path)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
        ):
            result = schedule_for_deal({})
        assert isinstance(result, dict)

    def test_invalid_sender_email_returns_skipped_no_recipient(self, tmp_path):
        store = _make_store(tmp_path)
        audit = _make_audit(tmp_path)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
        ):
            result = schedule_for_deal({**_deal(), "sender_email": "not-an-email"})
        assert result["status"] == "skipped"
        assert result["reason"] == "no_recipient"

    def test_not_discord_notified_returns_skipped(self, tmp_path):
        store = _make_store(tmp_path)
        audit = _make_audit(tmp_path)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.scheduler._is_discord_notified", return_value=False
            ),
        ):
            result = schedule_for_deal(_deal())
        assert result["status"] == "skipped"
        assert result["reason"] == "not_discord_notified"

    def test_duplicate_active_entry_returns_skipped_duplicate(self, tmp_path):
        gid = "msg_dupe"
        existing = _approved_email(gmail_message_id=gid)
        store = _make_store(tmp_path, emails=[existing])
        audit = _make_audit(tmp_path)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.scheduler._is_discord_notified", return_value=True
            ),
        ):
            result = schedule_for_deal({**_deal(), "gmail_message_id": gid})
        assert result["status"] == "skipped"
        assert result["reason"] == "duplicate"

    def test_scheduler_error_audit_event_written_on_exception(self, tmp_path):
        audit = _make_audit(tmp_path)
        with (
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.queue_store.get_store", side_effect=RuntimeError("boom")
            ),
            mock.patch(
                "email_scheduler.scheduler._is_discord_notified", return_value=True
            ),
        ):
            result = schedule_for_deal(_deal())
        assert result["status"] == "error"
        events = audit.get_events()
        assert any(e.event_type == EventType.SCHEDULER_ERROR.value for e in events)

    def test_exception_inside_schedule_never_raises(self, tmp_path):
        audit = _make_audit(tmp_path)
        with (
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch(
                "email_scheduler.queue_store.get_store", side_effect=RuntimeError("boom")
            ),
            mock.patch(
                "email_scheduler.scheduler._is_discord_notified", return_value=True
            ),
        ):
            result = schedule_for_deal(_deal())
        assert isinstance(result, dict)

    def test_scheduled_audit_event_written_on_success(self, tmp_path):
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


# ── T025: is_business_hours + next_business_window + dispatch_pending ─────────


# Anchor datetimes:
# Monday 2026-07-27 (BST = UTC+1, so 08:00 UTC = 09:00 BST, 16:00 UTC = 17:00 BST)
_MON_BST_09_UTC = datetime(2026, 7, 27, 8, 0, 0, tzinfo=timezone.utc)   # 09:00 BST
_MON_BST_12_UTC = datetime(2026, 7, 27, 11, 0, 0, tzinfo=timezone.utc)  # 12:00 BST
_MON_BST_17_UTC = datetime(2026, 7, 27, 16, 0, 0, tzinfo=timezone.utc)  # 17:00 BST (closed)
_MON_BST_08_UTC = datetime(2026, 7, 27, 7, 59, 0, tzinfo=timezone.utc)  # 08:59 BST (closed)

# Saturday 2026-08-01 UTC
_SAT_UTC = datetime(2026, 8, 1, 11, 0, 0, tzinfo=timezone.utc)

# Winter: Monday 2026-12-14 (GMT = UTC+0)
_MON_GMT_09 = datetime(2026, 12, 14, 9, 0, 0, tzinfo=timezone.utc)   # 09:00 GMT
_MON_GMT_17 = datetime(2026, 12, 14, 17, 0, 0, tzinfo=timezone.utc)  # 17:00 GMT (closed)


class TestIsBusinessHours:
    def test_inside_window_returns_true(self):
        assert is_business_hours(_MON_BST_12_UTC) is True

    def test_saturday_returns_false(self):
        assert is_business_hours(_SAT_UTC) is False

    def test_exactly_at_17_returns_false(self):
        assert is_business_hours(_MON_BST_17_UTC) is False

    def test_exactly_at_09_bst_returns_true(self):
        assert is_business_hours(_MON_BST_09_UTC) is True

    def test_dst_april_morning_08_utc_is_open(self):
        # April BST: 08:15 UTC = 09:15 BST → open
        april_utc = datetime(2026, 4, 6, 8, 15, 0, tzinfo=timezone.utc)
        assert is_business_hours(april_utc) is True

    def test_dst_april_17_utc_is_closed(self):
        # April BST: 16:00 UTC = 17:00 BST → closed
        april_utc = datetime(2026, 4, 6, 16, 0, 0, tzinfo=timezone.utc)
        assert is_business_hours(april_utc) is False

    def test_winter_monday_09_open(self):
        assert is_business_hours(_MON_GMT_09) is True

    def test_winter_monday_17_closed(self):
        assert is_business_hours(_MON_GMT_17) is False

    def test_before_09_closed(self):
        assert is_business_hours(_MON_BST_08_UTC) is False


class TestNextBusinessWindow:
    def test_already_inside_window_unchanged(self):
        result = next_business_window(_MON_BST_12_UTC)
        assert result == _MON_BST_12_UTC

    def test_saturday_advances_to_monday(self):
        result = next_business_window(_SAT_UTC)
        local_result = result.astimezone(timezone.utc)
        assert local_result > _SAT_UTC
        # Result should be on a weekday (Mon=0)
        from zoneinfo import ZoneInfo
        london = ZoneInfo("Europe/London")
        local = result.astimezone(london)
        assert local.weekday() < 5
        assert local.hour == 9

    def test_after_17_advances_to_next_day_09(self):
        result = next_business_window(_MON_BST_17_UTC)
        from zoneinfo import ZoneInfo
        london = ZoneInfo("Europe/London")
        local = result.astimezone(london)
        assert local.hour == 9

    def test_before_09_advances_to_09_same_day(self):
        result = next_business_window(_MON_BST_08_UTC)
        from zoneinfo import ZoneInfo
        london = ZoneInfo("Europe/London")
        local = result.astimezone(london)
        assert local.hour == 9
        assert local.weekday() == 0  # Monday


class TestDispatchPending:
    def _make_cfg(self, tmp_path):
        from email_scheduler.config import EmailSchedulerConfig
        return EmailSchedulerConfig(
            gmail_credentials_path="/tmp/creds.json",
            email_from_address="sender@example.com",
            email_queue_path=str(tmp_path / "queue.json"),
            email_audit_log_path=str(tmp_path / "audit.log"),
            email_template_path=None,
            email_enabled=True,
        )

    def test_dispatch_pending_returns_dict(self, tmp_path):
        store = _make_store(tmp_path)
        audit = _make_audit(tmp_path)
        cfg = self._make_cfg(tmp_path)

        mock_service = mock.MagicMock()
        mock_service.users().messages().send().execute.return_value = {"id": "sent_id"}

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch("email_scheduler.auth.build_send_service", return_value=mock_service),
            mock.patch("email_scheduler.scheduler.is_business_hours", return_value=False),
        ):
            result = dispatch_pending()
        assert isinstance(result, dict)
        assert "dispatched" in result
        assert "skipped" in result
        assert "failed" in result

    def test_dispatch_outside_business_hours_skips_all(self, tmp_path):
        em = _approved_email()
        store = _make_store(tmp_path, emails=[em])
        audit = _make_audit(tmp_path)
        cfg = self._make_cfg(tmp_path)

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch("email_scheduler.scheduler.is_business_hours", return_value=False),
        ):
            result = dispatch_pending()
        assert result["dispatched"] == 0
        assert result["skipped"] >= 1

    def test_dispatch_inside_business_hours_sends_email(self, tmp_path):
        em = _approved_email()
        store = _make_store(tmp_path, emails=[em])
        audit = _make_audit(tmp_path)
        cfg = self._make_cfg(tmp_path)

        mock_service = mock.MagicMock()
        mock_service.users().messages().send().execute.return_value = {"id": "gm_001"}

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
        assert result["failed"] == 0

    def test_dispatch_gmail_failure_increments_retry_count(self, tmp_path):
        em = _approved_email(retry_count=0)
        store = _make_store(tmp_path, emails=[em])
        audit = _make_audit(tmp_path)
        cfg = self._make_cfg(tmp_path)

        mock_service = mock.MagicMock()
        mock_service.users().messages().send().execute.side_effect = RuntimeError("send failed")

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
        assert result["failed"] == 1
        found = store.get_by_id(em.id)
        assert found.retry_count == 1

    def test_dispatch_third_failure_sets_status_failed(self, tmp_path):
        em = _approved_email(retry_count=2, retry_after=None)
        store = _make_store(tmp_path, emails=[em])
        audit = _make_audit(tmp_path)
        cfg = self._make_cfg(tmp_path)

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
        assert found.retry_after is None

    def test_retry_after_in_future_skips_email(self, tmp_path):
        future = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        em = _approved_email(retry_count=1, retry_after=future)
        store = _make_store(tmp_path, emails=[em])
        audit = _make_audit(tmp_path)
        cfg = self._make_cfg(tmp_path)

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
            mock.patch("email_scheduler.scheduler.is_business_hours", return_value=True),
        ):
            result = dispatch_pending()
        assert result["skipped"] >= 1
        assert result["dispatched"] == 0

    def test_email_disabled_returns_zeros(self, tmp_path):
        from email_scheduler.config import EmailSchedulerConfig
        cfg_disabled = EmailSchedulerConfig(
            gmail_credentials_path="/tmp/creds.json",
            email_from_address="sender@example.com",
            email_queue_path=str(tmp_path / "queue.json"),
            email_audit_log_path=str(tmp_path / "audit.log"),
            email_template_path=None,
            email_enabled=False,
        )
        store = _make_store(tmp_path)
        audit = _make_audit(tmp_path)

        with (
            mock.patch("email_scheduler.config.load_email_config", return_value=cfg_disabled),
            mock.patch("email_scheduler.queue_store.get_store", return_value=store),
            mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=audit),
        ):
            result = dispatch_pending()
        assert result == {"dispatched": 0, "skipped": 0, "failed": 0}

    def test_config_incomplete_does_not_raise(self, monkeypatch):
        monkeypatch.delenv("GMAIL_CREDENTIALS_PATH", raising=False)
        monkeypatch.delenv("EMAIL_FROM_ADDRESS", raising=False)
        result = dispatch_pending()
        assert isinstance(result, dict)

    def test_dispatch_never_raises_on_unhandled_exception(self, tmp_path):
        with (
            mock.patch(
                "email_scheduler.config.load_email_config",
                side_effect=RuntimeError("unexpected"),
            ),
        ):
            result = dispatch_pending()
        assert isinstance(result, dict)
