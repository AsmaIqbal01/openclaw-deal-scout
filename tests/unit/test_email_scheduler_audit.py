"""Unit tests for AuditLogger and startup recovery — T031."""
from __future__ import annotations

import dataclasses
import json
import threading
import uuid
from pathlib import Path
from unittest import mock

import pytest

from email_scheduler.audit_logger import AuditLogger
from email_scheduler.models import EmailEvent, EventType
from email_scheduler.queue_store import EmailQueueStore


def _event(event_type: str = "scheduled", email_id: str | None = None) -> EmailEvent:
    return EmailEvent(
        event_id=str(uuid.uuid4()),
        email_id=email_id or str(uuid.uuid4()),
        gmail_message_id="msg_" + str(uuid.uuid4())[:6],
        event_type=event_type,
        timestamp="2026-07-22T10:00:00Z",
        actor="system",
        recipient_email="buyer@example.com",
    )


@pytest.fixture
def audit(tmp_path) -> AuditLogger:
    return AuditLogger(tmp_path / "audit.log")


class TestAuditLoggerWrite:
    def test_write_appends_json_line_to_file(self, audit, tmp_path):
        ev = _event()
        audit.write(ev)
        lines = (tmp_path / "audit.log").read_text().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event_id"] == ev.event_id

    def test_all_fields_serialised(self, audit, tmp_path):
        ev = _event()
        audit.write(ev)
        raw = json.loads((tmp_path / "audit.log").read_text().splitlines()[0])
        for field in dataclasses.fields(ev):
            assert field.name in raw

    def test_file_created_when_absent(self, tmp_path):
        path = tmp_path / "sub" / "audit.log"
        logger = AuditLogger(path)
        ev = _event()
        logger.write(ev)
        assert path.exists()

    def test_multiple_writes_each_produce_one_line(self, audit, tmp_path):
        for _ in range(5):
            audit.write(_event())
        lines = (tmp_path / "audit.log").read_text().splitlines()
        assert len(lines) == 5

    def test_thread_safe_concurrent_writes(self, audit, tmp_path):
        errors: list[Exception] = []

        def _write():
            try:
                for _ in range(5):
                    audit.write(_event())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_write) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        lines = (tmp_path / "audit.log").read_text().splitlines()
        for line in lines:
            json.loads(line)  # each line must be valid JSON


class TestGetEvents:
    def test_get_events_returns_newest_first(self, audit):
        ev1 = _event()
        ev2 = _event()
        audit.write(ev1)
        audit.write(ev2)
        events = audit.get_events()
        assert events[0].event_id == ev2.event_id
        assert events[1].event_id == ev1.event_id

    def test_get_events_returns_snapshot(self, audit):
        audit.write(_event())
        snap = audit.get_events()
        audit.write(_event())
        assert len(snap) == 1

    def test_get_events_empty_when_no_writes(self, audit):
        assert audit.get_events() == []


class TestLoadExistingEvents:
    def test_loads_existing_events_from_file_at_startup(self, tmp_path):
        ev = _event()
        (tmp_path / "audit.log").write_text(
            json.dumps(dataclasses.asdict(ev)) + "\n", encoding="utf-8"
        )
        logger = AuditLogger(tmp_path / "audit.log")
        events = logger.get_events()
        assert len(events) == 1
        assert events[0].event_id == ev.event_id

    def test_corrupted_lines_skipped_on_load(self, tmp_path):
        ev = _event()
        (tmp_path / "audit.log").write_text(
            "not-json\n" + json.dumps(dataclasses.asdict(ev)) + "\n",
            encoding="utf-8",
        )
        logger = AuditLogger(tmp_path / "audit.log")
        assert len(logger.get_events()) == 1


class TestStartupRecovery:
    def _make_store(self, tmp_path, emails=None) -> EmailQueueStore:
        s = EmailQueueStore(tmp_path / "q.json")
        s.load()
        if emails:
            for em in emails:
                s._emails.append(em)
            s._write_locked()
        return s

    def _approved_email(self, tmp_path, email_id: str, gid: str) -> None:
        from email_scheduler.models import ScheduledEmail
        em = ScheduledEmail(
            id=email_id,
            gmail_message_id=gid,
            recipient_name="Bob",
            recipient_email="bob@example.com",
            subject="T",
            body="B",
            status="approved",
            proposed_send_at="2026-07-28T09:00:00Z",
            created_at="2026-07-22T09:00:00Z",
        )
        return em

    def test_sent_audit_event_repairs_approved_queue_entry(self, tmp_path):
        email_id = str(uuid.uuid4())
        gid = "msg_repair"
        em = self._approved_email(tmp_path, email_id, gid)
        store = self._make_store(tmp_path, emails=[em])
        audit = AuditLogger(tmp_path / "audit.log")

        sent_event = EmailEvent(
            event_id=str(uuid.uuid4()),
            email_id=email_id,
            gmail_message_id=gid,
            event_type="sent",
            timestamp="2026-07-22T10:05:00Z",
            actor="system",
        )
        audit.write(sent_event)

        store._repair_from_audit(tmp_path / "audit.log", audit)

        found = store.get_by_id(email_id)
        assert found.status == "sent"
        assert found.sent_at == "2026-07-22T10:05:00Z"

    def test_recovery_writes_recovered_audit_event(self, tmp_path):
        email_id = str(uuid.uuid4())
        gid = "msg_recover"
        em = self._approved_email(tmp_path, email_id, gid)
        store = self._make_store(tmp_path, emails=[em])
        audit = AuditLogger(tmp_path / "audit.log")

        sent_event = EmailEvent(
            event_id=str(uuid.uuid4()),
            email_id=email_id,
            gmail_message_id=gid,
            event_type="sent",
            timestamp="2026-07-22T10:05:00Z",
            actor="system",
        )
        audit.write(sent_event)
        store._repair_from_audit(tmp_path / "audit.log", audit)

        events = audit.get_events()
        recovered_events = [e for e in events if e.event_type == EventType.RECOVERED.value]
        assert len(recovered_events) == 1

    def test_corrupted_audit_log_writes_recovery_warning(self, tmp_path):
        store = self._make_store(tmp_path)
        audit = AuditLogger(tmp_path / "audit.log")
        (tmp_path / "audit.log").write_text("not-json\n", encoding="utf-8")
        # Re-init audit to pick up the corrupted file
        audit2 = AuditLogger(tmp_path / "audit.log")

        store._repair_from_audit(tmp_path / "audit.log", audit2)

        events = audit2.get_events()
        warn_events = [e for e in events if e.event_type == EventType.RECOVERY_WARN.value]
        assert len(warn_events) == 1

    def test_absent_audit_log_repair_no_error(self, tmp_path):
        store = self._make_store(tmp_path)
        audit = AuditLogger(tmp_path / "audit.log")
        absent = tmp_path / "nonexistent.log"
        store._repair_from_audit(absent, audit)  # must not raise
