"""Unit tests for pipeline_orchestrator.cycle_logger — T008."""
from __future__ import annotations

import json
import logging
import logging.handlers

import pytest

from pipeline_orchestrator.config import PipelineConfig
from pipeline_orchestrator.cycle_logger import CycleLogger


def _make_config(tmp_path) -> PipelineConfig:
    return PipelineConfig(
        state_store_path=tmp_path / "processed_ids.json",
        poll_interval_minutes=15,
        lock_timeout_minutes=30,
        log_path=tmp_path / "pipeline.log",
        log_max_bytes=1_048_576,
        log_backup_count=3,
        max_pending_retries=10,
        scheduler_mode="loop",
    )


class TestCycleLogger:
    def test_emit_writes_valid_json(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)
        cl.emit_cycle_summary(
            ts="2026-07-22T14:00:00Z",
            emails_processed=3,
            crm_logged=2,
            notified=1,
            pending=0,
            errors=[],
        )
        lines = config.log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["ts"] == "2026-07-22T14:00:00Z"
        assert record["emails_processed"] == 3
        assert record["crm_logged"] == 2
        assert record["notified"] == 1
        assert record["pending"] == 0
        assert record["errors"] == []

    def test_emit_includes_all_six_fields(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)
        cl.emit_cycle_summary(
            ts="2026-07-22T14:00:00Z",
            emails_processed=0,
            crm_logged=0,
            notified=0,
            pending=0,
            errors=[],
        )
        lines = config.log_path.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert set(record.keys()) == {"ts", "emails_processed", "crm_logged", "notified", "pending", "errors"}

    def test_emit_errors_list_preserved(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)
        cl.emit_cycle_summary(
            ts="2026-07-22T14:00:00Z",
            emails_processed=0,
            crm_logged=0,
            notified=0,
            pending=2,
            errors=["quota_exhausted", "crm_suspended"],
        )
        lines = config.log_path.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["errors"] == ["quota_exhausted", "crm_suspended"]

    def test_rotating_handler_configured(self, tmp_path):
        config = PipelineConfig(
            state_store_path=tmp_path / "store.json",
            poll_interval_minutes=15,
            lock_timeout_minutes=30,
            log_path=tmp_path / "pipeline.log",
            log_max_bytes=5000,
            log_backup_count=2,
            max_pending_retries=10,
            scheduler_mode="loop",
        )
        cl = CycleLogger(config)
        handler = cl._logger.handlers[0]
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert handler.maxBytes == 5000
        assert handler.backupCount == 2

    def test_multiple_cycles_produce_multiple_lines(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)
        for i in range(3):
            cl.emit_cycle_summary(
                ts=f"2026-07-22T1{i}:00:00Z",
                emails_processed=i,
                crm_logged=0,
                notified=0,
                pending=0,
                errors=[],
            )
        lines = config.log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # each line must be valid JSON

    def test_log_rotation_occurs(self, tmp_path):
        config = PipelineConfig(
            state_store_path=tmp_path / "store.json",
            poll_interval_minutes=15,
            lock_timeout_minutes=30,
            log_path=tmp_path / "pipeline.log",
            log_max_bytes=200,
            log_backup_count=2,
            max_pending_retries=10,
            scheduler_mode="loop",
        )
        cl = CycleLogger(config)
        # Write enough to trigger rotation
        for i in range(20):
            cl.emit_cycle_summary(
                ts="2026-07-22T14:00:00Z",
                emails_processed=i,
                crm_logged=0,
                notified=0,
                pending=0,
                errors=[],
            )
        # Main log file must not grow unbounded
        assert config.log_path.stat().st_size <= config.log_max_bytes * 3
