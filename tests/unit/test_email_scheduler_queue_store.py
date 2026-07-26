"""Unit tests for EmailQueueStore — T012 (create/list/dedup) + T018 (approve/cancel)."""
from __future__ import annotations

import dataclasses
import json
import threading
import uuid
from pathlib import Path

import pytest

from email_scheduler.models import ScheduledEmail
from email_scheduler.queue_store import ACTIVE_STATUSES, EmailQueueStore


def _email(
    status: str = "scheduled",
    gmail_message_id: str | None = None,
    recipient_email: str = "buyer@example.com",
) -> ScheduledEmail:
    return ScheduledEmail(
        id=str(uuid.uuid4()),
        gmail_message_id=gmail_message_id or str(uuid.uuid4()),
        recipient_name="Alice",
        recipient_email=recipient_email,
        subject="Test subject",
        body="Test body",
        status=status,
        proposed_send_at="2026-07-28T09:00:00Z",
        created_at="2026-07-22T10:00:00Z",
    )


@pytest.fixture
def store(tmp_path) -> EmailQueueStore:
    s = EmailQueueStore(tmp_path / "email_queue.json")
    s.load()
    return s


# ── T012: create / list / dedup ───────────────────────────────────────────────


class TestCreate:
    def test_store_starts_empty(self, store):
        assert store.list_emails() == []

    def test_create_returns_created(self, store):
        result, _ = store.create(_email())
        assert result == "created"

    def test_create_adds_one_entry(self, store):
        store.create(_email())
        assert len(store.list_emails()) == 1

    def test_create_persists_to_disk(self, store, tmp_path):
        em = _email()
        store.create(em)
        raw = json.loads((tmp_path / "email_queue.json").read_text())
        assert len(raw["emails"]) == 1
        assert raw["version"] == 1

    def test_file_created_when_absent(self, tmp_path):
        path = tmp_path / "sub" / "q.json"
        s = EmailQueueStore(path)
        s.load()
        assert path.exists()

    def test_get_by_id_returns_entry(self, store):
        em = _email()
        store.create(em)
        found = store.get_by_id(em.id)
        assert found is not None and found.id == em.id

    def test_get_by_id_returns_none_for_unknown(self, store):
        assert store.get_by_id("does-not-exist") is None

    def test_list_emails_filters_by_status(self, store):
        sched = _email(status="scheduled")
        appr = _email(status="approved")
        store.create(sched)
        store._emails.append(appr)
        result = store.list_emails(status_filter="scheduled")
        assert len(result) == 1 and result[0].id == sched.id

    def test_list_emails_no_filter_returns_all(self, store):
        for _ in range(3):
            store._emails.append(_email())
        assert len(store.list_emails()) == 3


class TestDeduplicate:
    def test_dedup_blocks_create_for_scheduled(self, store):
        gid = "msg_sched"
        store.create(_email(status="scheduled", gmail_message_id=gid))
        result, reason = store.create(_email(status="scheduled", gmail_message_id=gid))
        assert result == "skipped" and reason == "duplicate"

    def test_dedup_blocks_create_for_approved(self, store):
        gid = "msg_appr"
        store._emails.append(_email(status="approved", gmail_message_id=gid))
        result, _ = store.create(_email(status="scheduled", gmail_message_id=gid))
        assert result == "skipped"

    def test_dedup_blocks_create_for_sent(self, store):
        gid = "msg_sent"
        store._emails.append(_email(status="sent", gmail_message_id=gid))
        result, _ = store.create(_email(status="scheduled", gmail_message_id=gid))
        assert result == "skipped"

    def test_dedup_allows_create_after_cancelled(self, store):
        gid = "msg_cancelled"
        store._emails.append(_email(status="cancelled", gmail_message_id=gid))
        result, _ = store.create(_email(status="scheduled", gmail_message_id=gid))
        assert result == "created"

    def test_dedup_allows_create_after_failed(self, store):
        gid = "msg_failed"
        store._emails.append(_email(status="failed", gmail_message_id=gid))
        result, _ = store.create(_email(status="scheduled", gmail_message_id=gid))
        assert result == "created"


class TestLoad:
    def test_load_returns_empty_when_file_absent(self, tmp_path):
        s = EmailQueueStore(tmp_path / "q.json")
        s.load()
        assert s.list_emails() == []

    def test_load_restores_entries_from_valid_file(self, tmp_path):
        em = _email()
        data = {"version": 1, "emails": [dataclasses.asdict(em)]}
        (tmp_path / "q.json").write_text(json.dumps(data))
        s = EmailQueueStore(tmp_path / "q.json")
        s.load()
        assert len(s.list_emails()) == 1

    def test_load_corrupted_file_inits_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{ not valid json", encoding="utf-8")
        s = EmailQueueStore(path)
        s.load()
        assert s.list_emails() == []


class TestThreadSafety:
    def test_concurrent_creates_all_succeed(self, store):
        errors: list[Exception] = []

        def _create():
            try:
                store.create(_email())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_create) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(store.list_emails()) == 10


# ── T018: approve / cancel ────────────────────────────────────────────────────


class TestApprove:
    def test_approve_changes_status_to_approved(self, store):
        em = _email(status="scheduled")
        store.create(em)
        result = store.approve(em.id)
        assert result.status == "approved"

    def test_approve_sets_approved_at(self, store):
        em = _email(status="scheduled")
        store.create(em)
        result = store.approve(em.id)
        assert result.approved_at is not None

    def test_approve_persists_to_disk(self, store, tmp_path):
        em = _email(status="scheduled")
        store.create(em)
        store.approve(em.id)
        raw = json.loads((tmp_path / "email_queue.json").read_text())
        assert raw["emails"][0]["status"] == "approved"

    def test_approve_idempotent_same_timestamp(self, store):
        em = _email(status="scheduled")
        store.create(em)
        first = store.approve(em.id)
        second = store.approve(em.id)
        assert second.approved_at == first.approved_at
        assert second.status == "approved"

    def test_approve_unknown_id_raises_key_error(self, store):
        with pytest.raises(KeyError):
            store.approve("nonexistent")

    def test_approve_on_sent_raises_value_error(self, store):
        em = _email(status="sent")
        store._emails.append(em)
        with pytest.raises(ValueError, match="sent"):
            store.approve(em.id)

    def test_approve_on_cancelled_raises_value_error(self, store):
        em = _email(status="cancelled")
        store._emails.append(em)
        with pytest.raises(ValueError, match="cancelled"):
            store.approve(em.id)

    def test_approve_on_failed_raises_value_error(self, store):
        em = _email(status="failed")
        store._emails.append(em)
        with pytest.raises(ValueError, match="failed"):
            store.approve(em.id)


class TestCancel:
    def test_cancel_scheduled_succeeds(self, store):
        em = _email(status="scheduled")
        store.create(em)
        result = store.cancel(em.id)
        assert result.status == "cancelled"
        assert result.cancelled_at is not None

    def test_cancel_approved_succeeds(self, store):
        em = _email(status="approved")
        store._emails.append(em)
        result = store.cancel(em.id)
        assert result.status == "cancelled"

    def test_cancel_failed_succeeds(self, store):
        em = _email(status="failed")
        store._emails.append(em)
        result = store.cancel(em.id)
        assert result.status == "cancelled"

    def test_cancel_sent_raises_value_error(self, store):
        em = _email(status="sent")
        store._emails.append(em)
        with pytest.raises(ValueError, match="sent"):
            store.cancel(em.id)

    def test_cancel_idempotent(self, store):
        em = _email(status="scheduled")
        store.create(em)
        first = store.cancel(em.id)
        second = store.cancel(em.id)
        assert second.cancelled_at == first.cancelled_at

    def test_cancel_unknown_id_raises_key_error(self, store):
        with pytest.raises(KeyError):
            store.cancel("nonexistent")

    def test_cancel_persists_to_disk(self, store, tmp_path):
        em = _email(status="scheduled")
        store.create(em)
        store.cancel(em.id)
        raw = json.loads((tmp_path / "email_queue.json").read_text())
        assert raw["emails"][0]["status"] == "cancelled"


class TestMarkSentAndRetry:
    def test_mark_sent_updates_status(self, store):
        em = _email(status="approved")
        store._emails.append(em)
        ok = store.mark_sent(em.id, "2026-07-22T10:30:00Z")
        assert ok is True
        found = store.get_by_id(em.id)
        assert found.status == "sent"
        assert found.sent_at == "2026-07-22T10:30:00Z"

    def test_mark_retry_below_limit_keeps_approved(self, store):
        em = _email(status="approved")
        store._emails.append(em)
        result = store.mark_retry(em.id, 1, "2026-07-22T10:00:00Z", "2026-07-22T10:01:00Z", "err")
        assert result.status == "approved"
        assert result.retry_count == 1

    def test_mark_retry_at_limit_sets_failed(self, store):
        em = _email(status="approved")
        store._emails.append(em)
        result = store.mark_retry(em.id, 3, "2026-07-22T10:05:00Z", None, "max retries")
        assert result.status == "failed"
        assert result.retry_after is None
