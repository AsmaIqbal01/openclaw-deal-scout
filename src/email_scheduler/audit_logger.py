"""AuditLogger — thread-safe JSONL append to email_audit.log via logging.FileHandler."""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
from pathlib import Path

from email_scheduler.models import EmailEvent

_module_logger = logging.getLogger(__name__)

_audit_logger: "AuditLogger | None" = None
_audit_logger_lock = threading.Lock()


def get_audit_logger() -> "AuditLogger":
    global _audit_logger
    if _audit_logger is None:
        with _audit_logger_lock:
            if _audit_logger is None:
                from email_scheduler.config import load_email_config
                cfg = load_email_config()
                _audit_logger = AuditLogger(Path(cfg.email_audit_log_path))
    return _audit_logger


class AuditLogger:
    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._events: list[EmailEvent] = []
        log_path.parent.mkdir(parents=True, exist_ok=True)

        handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))

        self._logger = logging.getLogger(f"email_scheduler.audit.{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._logger.addHandler(handler)

        self._load_existing_events()

    def _load_existing_events(self) -> None:
        """Populate in-memory event list from existing log file (called once at startup)."""
        try:
            with open(self._path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        self._events.append(EmailEvent(**data))
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass
        except FileNotFoundError:
            pass

    def write(self, event: EmailEvent) -> None:
        """Append event to the audit log and in-memory list. Thread-safe via logging internals."""
        self._events.append(event)
        try:
            self._logger.info(json.dumps(dataclasses.asdict(event)))
        except Exception:
            _module_logger.exception(
                "audit_logger: failed to write event %s", event.event_id
            )

    def get_events(self) -> list[EmailEvent]:
        """Return a snapshot of all events, newest first."""
        return list(reversed(self._events))
