"""Tests for openclaw_gateway.tools.pipeline MCP tool functions."""
from __future__ import annotations

from unittest.mock import MagicMock
from pathlib import Path

import pytest

import openclaw_gateway.readers as _readers_mod
import openclaw_gateway.server as _srv_mod
import pipeline_orchestrator.runner as _runner_mod
from openclaw_gateway.tools.pipeline import get_deals, get_pipeline_cycles, get_quota_usage, run_cycle
from pipeline_orchestrator.config import PipelineConfig

_FAKE_CYCLE = {
    "ts": "2026-07-24T10:00:00Z",
    "emails_processed": 10,
    "crm_logged": 3,
    "notified": 3,
    "pending": 0,
    "errors": [],
    "duration_seconds": 20.0,
}

_FAKE_DEAL = {
    "gmail_message_id": "id1",
    "processed_at": "2026-07-24T00:00:00Z",
    "sender_name": "Alice Smith",
    "sender_email": "alice@example.com",
    "subject": "Partnership Offer",
    "deal_type": "partnership",
    "confidence_score": 0.9,
    "crm_status": "logged",
    "crm_retry_count": 0,
    "hubspot_deal_id": "123456",
    "notify_status": "sent",
    "notify_retry_count": 0,
}

_FAKE_QUOTA = {
    "estimated_requests_today": 22,
    "daily_free_tier_limit": 1500,
    "estimated_remaining": 1478,
    "pct_used": 1.47,
    "window_date": "2026-07-24",
    "cycles_today": 2,
    "has_quota_error_today": False,
}


# ── get_pipeline_cycles ────────────────────────────────────────────────────────

class TestGetPipelineCycles:

    def test_has_required_keys(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "read_pipeline_log", lambda n, cfg: [])
        result = get_pipeline_cycles()
        assert "cycles" in result
        assert "total_in_log" in result

    def test_returns_limited_cycles(self, monkeypatch):
        cycles = [_FAKE_CYCLE] * 5
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "read_pipeline_log", lambda n, cfg: cycles[:n])
        result = get_pipeline_cycles(limit=3)
        assert len(result["cycles"]) == 3

    def test_total_in_log_counts_all(self, monkeypatch):
        cycles = [_FAKE_CYCLE] * 5
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "read_pipeline_log", lambda n, cfg: cycles[:n])
        result = get_pipeline_cycles(limit=2)
        assert result["total_in_log"] == 5

    def test_empty_log_returns_zero_total(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "read_pipeline_log", lambda n, cfg: [])
        result = get_pipeline_cycles(limit=5)
        assert result == {"cycles": [], "total_in_log": 0}


# ── get_deals ──────────────────────────────────────────────────────────────────

class TestGetDeals:

    def test_has_required_keys(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "read_deals", lambda limit, status, cfg: [])
        result = get_deals()
        assert "deals" in result
        assert "total_deals" in result
        assert "filtered_by" in result

    def test_filtered_by_matches_status_arg(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "read_deals", lambda limit, status, cfg: [])
        result = get_deals(status="crm_pending")
        assert result["filtered_by"] == "crm_pending"

    def test_total_deals_is_unfiltered_count(self, monkeypatch):
        all_deals = [_FAKE_DEAL] * 3
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())

        def mock_read(limit, status, cfg):
            if status == "all":
                return all_deals[:limit]
            return []

        monkeypatch.setattr(_readers_mod, "read_deals", mock_read)
        result = get_deals(limit=10, status="crm_pending")
        assert result["total_deals"] == 3
        assert result["deals"] == []

    def test_deals_list_from_reader(self, monkeypatch):
        deals = [_FAKE_DEAL]
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "read_deals", lambda limit, status, cfg: deals)
        result = get_deals()
        assert result["deals"] == deals

    def test_default_status_is_all(self, monkeypatch):
        received = []
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())

        def capture(limit, status, cfg):
            received.append(status)
            return []

        monkeypatch.setattr(_readers_mod, "read_deals", capture)
        get_deals()
        assert "all" in received


# ── get_quota_usage ────────────────────────────────────────────────────────────

class TestGetQuotaUsage:

    def test_returns_quota_dict(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "compute_quota_usage", lambda cfg: _FAKE_QUOTA)
        result = get_quota_usage()
        assert result == _FAKE_QUOTA

    def test_has_all_seven_keys(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_config", MagicMock())
        monkeypatch.setattr(_readers_mod, "compute_quota_usage", lambda cfg: _FAKE_QUOTA)
        result = get_quota_usage()
        for key in (
            "estimated_requests_today", "daily_free_tier_limit", "estimated_remaining",
            "pct_used", "window_date", "cycles_today", "has_quota_error_today",
        ):
            assert key in result

    def test_passes_config_to_reader(self, monkeypatch):
        fake_config = MagicMock()
        monkeypatch.setattr(_srv_mod, "_config", fake_config)
        received = []

        def capture(cfg):
            received.append(cfg)
            return _FAKE_QUOTA

        monkeypatch.setattr(_readers_mod, "compute_quota_usage", capture)
        get_quota_usage()
        assert received == [fake_config]


# ── run_cycle (T025) ───────────────────────────────────────────────────────────

def _make_pipeline_config(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        state_store_path=tmp_path / "state.json",
        poll_interval_minutes=15,
        lock_timeout_minutes=30,
        log_path=tmp_path / "pipeline.log",
        log_max_bytes=1_048_576,
        log_backup_count=3,
        max_pending_retries=10,
        scheduler_mode="gateway",
    )


class TestRunCycle:

    def test_busy_path_returns_busy_dict(self, monkeypatch, tmp_path):
        from pipeline_orchestrator.lock import CycleLockActiveError

        cfg = _make_pipeline_config(tmp_path)
        monkeypatch.setattr(_srv_mod, "_config", cfg)

        def raise_busy(config, logger):
            raise CycleLockActiveError("test lock active")

        monkeypatch.setattr(_runner_mod, "run_cycle", raise_busy)
        result = run_cycle()
        assert result.get("busy") is True
        assert "message" in result

    def test_busy_message_contains_progress(self, monkeypatch, tmp_path):
        from pipeline_orchestrator.lock import CycleLockActiveError

        cfg = _make_pipeline_config(tmp_path)
        monkeypatch.setattr(_srv_mod, "_config", cfg)
        monkeypatch.setattr(_runner_mod, "run_cycle", lambda c, l: (_ for _ in ()).throw(CycleLockActiveError()))

        result = run_cycle()
        assert "progress" in result.get("message", "").lower() or "running" in result.get("message", "").lower()

    def test_success_returns_pipeline_cycle_dict(self, monkeypatch, tmp_path):
        cfg = _make_pipeline_config(tmp_path)
        monkeypatch.setattr(_srv_mod, "_config", cfg)

        def mock_run(config, cycle_logger):
            cycle_logger.emit_cycle_summary(
                ts="2026-07-24T10:00:00Z",
                emails_processed=5,
                crm_logged=1,
                notified=1,
                pending=0,
                errors=[],
            )

        monkeypatch.setattr(_runner_mod, "run_cycle", mock_run)
        result = run_cycle()
        assert result.get("emails_processed") == 5
        assert result.get("crm_logged") == 1
        assert "ts" in result
        assert "errors" in result

    def test_success_path_has_all_six_cycle_fields(self, monkeypatch, tmp_path):
        cfg = _make_pipeline_config(tmp_path)
        monkeypatch.setattr(_srv_mod, "_config", cfg)

        def mock_run(config, cycle_logger):
            cycle_logger.emit_cycle_summary(
                ts="2026-07-24T10:00:00Z",
                emails_processed=0,
                crm_logged=0,
                notified=0,
                pending=0,
                errors=[],
            )

        monkeypatch.setattr(_runner_mod, "run_cycle", mock_run)
        result = run_cycle()
        for key in ("ts", "emails_processed", "crm_logged", "notified", "pending", "errors"):
            assert key in result

    def test_cycle_running_cleared_after_success(self, monkeypatch, tmp_path):
        cfg = _make_pipeline_config(tmp_path)
        monkeypatch.setattr(_srv_mod, "_config", cfg)
        monkeypatch.setattr(_srv_mod, "_cycle_running", False)

        def mock_run(config, cycle_logger):
            cycle_logger.emit_cycle_summary(
                ts="2026-07-24T10:00:00Z",
                emails_processed=0, crm_logged=0, notified=0, pending=0, errors=[],
            )

        monkeypatch.setattr(_runner_mod, "run_cycle", mock_run)
        run_cycle()
        assert _srv_mod._cycle_running is False

    def test_last_cycle_at_set_after_success(self, monkeypatch, tmp_path):
        cfg = _make_pipeline_config(tmp_path)
        monkeypatch.setattr(_srv_mod, "_config", cfg)
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", None)

        def mock_run(config, cycle_logger):
            cycle_logger.emit_cycle_summary(
                ts="2026-07-24T10:00:00Z",
                emails_processed=0, crm_logged=0, notified=0, pending=0, errors=[],
            )

        monkeypatch.setattr(_runner_mod, "run_cycle", mock_run)
        run_cycle()
        assert _srv_mod._last_cycle_at is not None
