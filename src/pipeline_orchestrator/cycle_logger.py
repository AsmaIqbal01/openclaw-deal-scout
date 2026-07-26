"""CycleLogger — rotating file log with one JSON line per pipeline cycle."""
from __future__ import annotations

import json
import logging
import logging.handlers

from pipeline_orchestrator.config import PipelineConfig


class CycleLogger:
    def __init__(self, config: PipelineConfig) -> None:
        handler = logging.handlers.RotatingFileHandler(
            str(config.log_path),
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger = logging.getLogger("pipeline_orchestrator.cycle")
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            self._logger.addHandler(handler)
        else:
            self._logger.handlers.clear()
            self._logger.addHandler(handler)
        self._logger.propagate = False

    def emit_cycle_summary(
        self,
        *,
        ts: str,
        emails_processed: int,
        crm_logged: int,
        notified: int,
        pending: int,
        errors: list[str],
        emails_scheduled: int = 0,
        emails_dispatched: int = 0,
        emails_skipped: int = 0,
        emails_failed: int = 0,
    ) -> None:
        """Write one INFO-level JSON line. Email scheduling fields added when non-zero."""
        record: dict = {
            "ts": ts,
            "emails_processed": emails_processed,
            "crm_logged": crm_logged,
            "notified": notified,
            "pending": pending,
            "errors": errors,
        }
        if any((emails_scheduled, emails_dispatched, emails_skipped, emails_failed)):
            record["emails_scheduled"] = emails_scheduled
            record["emails_dispatched"] = emails_dispatched
            record["emails_skipped"] = emails_skipped
            record["emails_failed"] = emails_failed
        self._logger.info(json.dumps(record, separators=(",", ":")))
