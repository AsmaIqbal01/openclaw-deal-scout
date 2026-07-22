"""Unit tests for pipeline_orchestrator.runner — T012."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import google.auth.exceptions
import pytest

from gmail_intake.models import RateLimitExhaustedError
from pipeline_orchestrator.config import PipelineConfig
from pipeline_orchestrator.cycle_logger import CycleLogger
from pipeline_orchestrator.runner import run_cycle


def _make_config(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        state_store_path=tmp_path / "processed_ids.json",
        poll_interval_minutes=15,
        lock_timeout_minutes=30,
        log_path=tmp_path / "pipeline.log",
        log_max_bytes=1_048_576,
        log_backup_count=3,
        max_pending_retries=10,
        scheduler_mode="systemd",
    )


def _ok_step1(**overrides) -> dict:
    return {
        "status": "ok",
        "deals_extracted": [],
        "processed_count": 0,
        "skipped_count": 0,
        "error_details": None,
        **overrides,
    }


def _ok_step2(**overrides) -> dict:
    return {
        "status": "ok",
        "crm_logged": 0,
        "crm_pending": 0,
        "skipped": 0,
        "suspended": False,
        "error_details": None,
        **overrides,
    }


def _ok_step3(**overrides) -> dict:
    return {
        "status": "ok",
        "discord_notified": 0,
        "notify_pending": 0,
        "skipped": 0,
        "error_details": None,
        **overrides,
    }


def _parse_summary(log_path: Path) -> dict:
    line = log_path.read_text(encoding="utf-8").strip()
    return json.loads(line)


class TestRunCycleClean:
    def test_all_steps_called_zero_counts(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        mock_s1.assert_called_once()
        mock_s2.assert_called_once()
        mock_s3.assert_called_once()
        summary = _parse_summary(config.log_path)
        assert summary["emails_processed"] == 0
        assert summary["crm_logged"] == 0
        assert summary["notified"] == 0
        assert summary["errors"] == []

    def test_counts_propagated_from_step_returns(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(return_value=_ok_step1(processed_count=5))
        mock_s2 = MagicMock(return_value=_ok_step2(crm_logged=3, crm_pending=1))
        mock_s3 = MagicMock(return_value=_ok_step3(discord_notified=2, notify_pending=0))

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        summary = _parse_summary(config.log_path)
        assert summary["emails_processed"] == 5
        assert summary["crm_logged"] == 3
        assert summary["notified"] == 2
        assert summary["pending"] == 1


class TestRunCycleStep1Errors:
    def test_quota_exhausted_continues_steps_2_and_3(self, tmp_path):
        """FR-022: RateLimitExhaustedError → 'quota_exhausted' in errors, steps 2+3 still called."""
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(side_effect=RateLimitExhaustedError("quota"))
        mock_s2 = MagicMock(return_value=_ok_step2(crm_logged=1))
        mock_s3 = MagicMock(return_value=_ok_step3(discord_notified=1))

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        mock_s2.assert_called_once()
        mock_s3.assert_called_once()
        summary = _parse_summary(config.log_path)
        assert "quota_exhausted" in summary["errors"]

    def test_refresh_error_aborts_steps_2_and_3(self, tmp_path):
        """gmail_oauth_failed: steps 2 and 3 NOT called."""
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(side_effect=google.auth.exceptions.RefreshError("expired"))
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        mock_s2.assert_not_called()
        mock_s3.assert_not_called()
        summary = _parse_summary(config.log_path)
        assert "gmail_oauth_failed" in summary["errors"]

    def test_unhandled_exception_step1_aborts(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(side_effect=RuntimeError("crash"))
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        mock_s2.assert_not_called()
        mock_s3.assert_not_called()
        summary = _parse_summary(config.log_path)
        assert "unhandled_exception" in summary["errors"]

    def test_step1_status_error_auth_maps_to_gmail_oauth_failed(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(return_value={
            "status": "error",
            "deals_extracted": [],
            "processed_count": 0,
            "skipped_count": 0,
            "error_details": "auth token refresh failed",
        })
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        mock_s2.assert_not_called()
        mock_s3.assert_not_called()
        summary = _parse_summary(config.log_path)
        assert "gmail_oauth_failed" in summary["errors"]


class TestRunCycleStep2Errors:
    def test_step2_exception_step3_still_called(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(side_effect=RuntimeError("crm crash"))
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        mock_s3.assert_called_once()
        summary = _parse_summary(config.log_path)
        assert "unhandled_exception" in summary["errors"]

    def test_step2_suspended_adds_crm_suspended_error(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2(suspended=True))
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        mock_s3.assert_called_once()
        summary = _parse_summary(config.log_path)
        assert "crm_suspended" in summary["errors"]


class TestRunCycleLockBehavior:
    def test_lock_released_even_on_step1_exception(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(side_effect=RuntimeError("crash"))
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        assert not config.lock_path.exists()

    def test_summary_always_emitted(self, tmp_path):
        """Even when step 1 raises, the cycle summary is written."""
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        mock_s1 = AsyncMock(side_effect=google.auth.exceptions.RefreshError("expired"))
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        assert config.log_path.exists()
        summary = _parse_summary(config.log_path)
        assert "ts" in summary


class TestErrorTokenDeduplication:
    def test_error_tokens_appear_at_most_once(self, tmp_path):
        config = _make_config(tmp_path)
        cl = CycleLogger(config)

        # Both step 2 and step 3 have errors
        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(side_effect=RuntimeError("s2 crash"))
        mock_s3 = MagicMock(side_effect=RuntimeError("s3 crash"))

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, cl)

        summary = _parse_summary(config.log_path)
        errors = summary["errors"]
        assert errors.count("unhandled_exception") == 1
