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
    ) -> None:
        """Write one INFO-level JSON line with the six required fields."""
        record = {
            "ts": ts,
            "emails_processed": emails_processed,
            "crm_logged": crm_logged,
            "notified": notified,
            "pending": pending,
            "errors": errors,
        }
        self._logger.info(json.dumps(record, separators=(",", ":")))
