"""EmailQueueStore — in-memory queue with atomic JSON persistence and threading.Lock."""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from email_scheduler.models import EmailEvent, EventType, ScheduledEmail

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"scheduled", "approved", "sent"})

_store: "EmailQueueStore | None" = None
_store_lock = threading.Lock()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_store() -> "EmailQueueStore":
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                from email_scheduler.audit_logger import get_audit_logger
                from email_scheduler.config import load_email_config
                cfg = load_email_config()
                instance = EmailQueueStore(Path(cfg.email_queue_path))
                instance.load()
                instance._repair_from_audit(
                    Path(cfg.email_audit_log_path), get_audit_logger()
                )
                _store = instance
    return _store


class EmailQueueStore:
    def __init__(self, queue_path: Path) -> None:
        self._path = queue_path
        self._emails: list[ScheduledEmail] = []
        self._lock = threading.Lock()

    # ── Startup ───────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load queue from disk. Called once at startup (before repair)."""
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
            self._emails = [ScheduledEmail(**e) for e in data.get("emails", [])]
        except FileNotFoundError:
            self._emails = []
            self._write_locked()
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning(
                "email_queue.json corrupted at startup — initialising empty queue: %s", exc
            )
            self._emails = []
            self._write_locked()

    def _repair_from_audit(self, audit_log_path: Path, audit_logger) -> None:
        """
        Scan the audit log for 'sent' events and repair any queue entries still
        at 'approved' status (crash recovery). Called once at startup after load().
        """
        repaired: list[tuple[str, str]] = []  # (email_id, sent_at)
        corrupted = False

        try:
            with open(audit_log_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        corrupted = True
                        continue
                    if event.get("event_type") == "sent":
                        email_id = event.get("email_id")
                        sent_at = event.get("timestamp", _utcnow_iso())
                        for email in self._emails:
                            if email.id == email_id and email.status == "approved":
                                email.status = "sent"
                                email.sent_at = sent_at
                                repaired.append((email.id, sent_at))
        except FileNotFoundError:
            return
        except Exception as exc:
            logger.warning("startup recovery: failed to read audit log: %s", exc)
            return

        if corrupted:
            logger.warning(
                "startup recovery: audit log has corrupted lines (ignored during repair)"
            )
            try:
                audit_logger.write(
                    EmailEvent(
                        event_id=str(uuid.uuid4()),
                        email_id=None,
                        gmail_message_id=None,
                        event_type=EventType.RECOVERY_WARN.value,
                        timestamp=_utcnow_iso(),
                        actor="system",
                    )
                )
            except Exception:
                pass

        for email_id, sent_at in repaired:
            logger.info(
                "startup recovery: repaired email %s (approved→sent, sent_at=%s)",
                email_id,
                sent_at,
            )
            try:
                audit_logger.write(
                    EmailEvent(
                        event_id=str(uuid.uuid4()),
                        email_id=email_id,
                        gmail_message_id=None,
                        event_type=EventType.RECOVERED.value,
                        timestamp=_utcnow_iso(),
                        actor="system",
                    )
                )
            except Exception:
                pass

        if repaired:
            self._write_locked()

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _write_locked(self) -> None:
        """Atomically write current state to disk. Caller must hold self._lock or be in init context."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "emails": [dataclasses.asdict(e) for e in self._emails],
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(self._path.parent),
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            tmp_path = fh.name
        os.replace(tmp_path, str(self._path))

    # ── Read operations (brief lock) ──────────────────────────────────────────

    def list_emails(self, status_filter: str | None = None) -> list[ScheduledEmail]:
        with self._lock:
            if status_filter is None:
                return list(self._emails)
            return [e for e in self._emails if e.status == status_filter]

    def get_by_id(self, email_id: str) -> ScheduledEmail | None:
        with self._lock:
            return next((e for e in self._emails if e.id == email_id), None)

    def _find_active(self, gmail_message_id: str) -> ScheduledEmail | None:
        """Must be called while holding self._lock."""
        return next(
            (
                e for e in self._emails
                if e.gmail_message_id == gmail_message_id and e.status in ACTIVE_STATUSES
            ),
            None,
        )

    # ── Write operations ──────────────────────────────────────────────────────

    def create(self, email: ScheduledEmail) -> tuple[str, str]:
        """
        Create a new entry after dedup check.
        Returns ("created", "") or ("skipped", "duplicate").
        """
        with self._lock:
            if self._find_active(email.gmail_message_id) is not None:
                return "skipped", "duplicate"
            self._emails.append(email)
            self._write_locked()
            return "created", ""

    def approve(self, email_id: str) -> ScheduledEmail:
        """
        Transition to 'approved'. Idempotent if already approved.
        Raises KeyError if not found.
        Raises ValueError(current_status) for terminal transitions (sent/cancelled/failed).
        Raises OSError if disk write fails (in-memory state rolled back).
        """
        with self._lock:
            email = next((e for e in self._emails if e.id == email_id), None)
            if email is None:
                raise KeyError(email_id)
            if email.status == "approved":
                return email
            if email.status in ("sent", "cancelled", "failed"):
                raise ValueError(email.status)
            old_status, old_approved_at = email.status, email.approved_at
            email.status = "approved"
            email.approved_at = _utcnow_iso()
            try:
                self._write_locked()
            except OSError:
                email.status = old_status
                email.approved_at = old_approved_at
                raise
            return email

    def cancel(self, email_id: str) -> ScheduledEmail:
        """
        Transition to 'cancelled'. Idempotent if already cancelled.
        Permitted from: scheduled, approved, failed.
        Raises KeyError if not found.
        Raises ValueError(current_status) if email is 'sent' (only terminal that blocks cancel).
        Raises OSError if disk write fails (in-memory state rolled back).
        """
        with self._lock:
            email = next((e for e in self._emails if e.id == email_id), None)
            if email is None:
                raise KeyError(email_id)
            if email.status == "cancelled":
                return email
            if email.status == "sent":
                raise ValueError(email.status)
            old_status, old_cancelled_at = email.status, email.cancelled_at
            email.status = "cancelled"
            email.cancelled_at = _utcnow_iso()
            try:
                self._write_locked()
            except OSError:
                email.status = old_status
                email.cancelled_at = old_cancelled_at
                raise
            return email

    def mark_sent(self, email_id: str, sent_at: str) -> bool:
        """Mark an email as sent. Returns True if the update was applied."""
        with self._lock:
            email = next((e for e in self._emails if e.id == email_id), None)
            if email is None:
                return False
            email.status = "sent"
            email.sent_at = sent_at
            self._write_locked()
            return True

    def mark_retry(
        self,
        email_id: str,
        retry_count: int,
        failed_at: str,
        retry_after: str | None,
        last_error: str,
    ) -> ScheduledEmail | None:
        """
        Update retry state after a failed send attempt.
        If retry_count >= 3: sets status='failed', retry_after=None.
        Otherwise keeps status='approved' with updated retry_count and retry_after.
        """
        with self._lock:
            email = next((e for e in self._emails if e.id == email_id), None)
            if email is None:
                return None
            email.retry_count = retry_count
            email.failed_at = failed_at
            email.last_error = last_error
            if retry_count >= 3:
                email.status = "failed"
                email.retry_after = None
            else:
                email.retry_after = retry_after
            self._write_locked()
            return email
