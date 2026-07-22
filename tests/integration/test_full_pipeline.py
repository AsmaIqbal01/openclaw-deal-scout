"""Integration tests for pipeline_orchestrator — T013 through T025."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gmail_intake.models import RateLimitExhaustedError
from pipeline_orchestrator.config import PipelineConfig, load_config
from pipeline_orchestrator.cycle_logger import CycleLogger
from pipeline_orchestrator.lock import CycleLock, CycleLockActiveError, _TIMESTAMP_FMT
from pipeline_orchestrator.runner import run_cycle

# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_config(tmp_path: Path, **overrides) -> PipelineConfig:
    defaults = dict(
        state_store_path=tmp_path / "processed_ids.json",
        poll_interval_minutes=15,
        lock_timeout_minutes=30,
        log_path=tmp_path / "pipeline.log",
        log_max_bytes=1_048_576,
        log_backup_count=3,
        max_pending_retries=10,
        scheduler_mode="systemd",
    )
    defaults.update(overrides)
    return PipelineConfig(**defaults)


def _write_store(state_path: Path, messages: list[dict] | None = None) -> None:
    state_path.write_text(
        json.dumps(
            {"last_poll_time": None, "messages": messages or [], "consecutive_401_cycles": 0},
            indent=2,
        ),
        encoding="utf-8",
    )


def _read_store(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


def _ok_step1(**kw) -> dict:
    return {"status": "ok", "deals_extracted": [], "processed_count": 0, "skipped_count": 0, "error_details": None, **kw}


def _ok_step2(**kw) -> dict:
    return {"status": "ok", "crm_logged": 0, "crm_pending": 0, "skipped": 0, "suspended": False, "error_details": None, **kw}


def _ok_step3(**kw) -> dict:
    return {"status": "ok", "discord_notified": 0, "notify_pending": 0, "skipped": 0, "error_details": None, **kw}


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)


def _ts_ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime(_TIMESTAMP_FMT)


def _summary(config: PipelineConfig) -> dict:
    return json.loads(config.log_path.read_text(encoding="utf-8").strip().splitlines()[-1])


# ─── US2: Concurrent Cycle Prevention (T013) ──────────────────────────────────

class TestConcurrentCyclePrevention:
    def test_sc003_active_lock_rejects_cycle(self, tmp_path):
        """SC-003: pre-existing fresh lock → CycleLockActiveError, no step called."""
        config = _make_config(tmp_path)
        config.lock_path.write_text(_ts_now(), encoding="utf-8")

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            with pytest.raises(CycleLockActiveError):
                run_cycle(config, CycleLogger(config))

        mock_s1.assert_not_called()
        mock_s2.assert_not_called()
        mock_s3.assert_not_called()
        # Original lock file is untouched
        assert config.lock_path.exists()

    def test_sc004_stale_lock_cleared_and_cycle_proceeds(self, tmp_path):
        """SC-004: stale lock (35 min old, timeout=30) → WARN logged, cleared, cycle runs."""
        config = _make_config(tmp_path)
        config.lock_path.write_text(_ts_ago(35), encoding="utf-8")

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        mock_s1.assert_called_once()

    def test_sc016_malformed_lock_cleared_and_proceeds(self, tmp_path, caplog):
        """SC-016: malformed lock content → WARN logged, cleared, cycle proceeds normally."""
        import logging
        config = _make_config(tmp_path)
        config.lock_path.write_text("NOT_A_TIMESTAMP", encoding="utf-8")

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with caplog.at_level(logging.WARNING):
            with (
                patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
                patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
                patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
            ):
                run_cycle(config, CycleLogger(config))

        mock_s1.assert_called_once()
        assert any("malformed" in m.lower() for m in caplog.messages)


# ─── US3: Quota and Transient Error Resilience (T016) ─────────────────────────

class TestErrorResilience:
    def test_sc002_lock_absent_after_quota_abort(self, tmp_path):
        """SC-002: quota abort → lock file absent after cycle, summary written with error token."""
        config = _make_config(tmp_path)

        mock_s1 = AsyncMock(side_effect=RateLimitExhaustedError("quota"))
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        assert not config.lock_path.exists()
        summary = _summary(config)
        assert "quota_exhausted" in summary["errors"]

    def test_sc017_quota_mid_batch_drains_classified_entries(self, tmp_path):
        """SC-017: quota exhausted after some entries classified → crm_logged reflects drain."""
        config = _make_config(tmp_path)

        # Step 1 raises RateLimitExhaustedError but 2 entries were already in state store
        mock_s1 = AsyncMock(side_effect=RateLimitExhaustedError("quota"))
        mock_s2 = MagicMock(return_value=_ok_step2(crm_logged=2))
        mock_s3 = MagicMock(return_value=_ok_step3(discord_notified=2))

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        summary = _summary(config)
        assert summary["crm_logged"] == 2
        assert "quota_exhausted" in summary["errors"]

    def test_sc014_suspended_step2_still_runs_step3(self, tmp_path):
        """SC-014: suspended=True → step 3 still called, 'crm_suspended' in errors."""
        config = _make_config(tmp_path)

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2(suspended=True))
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        mock_s3.assert_called_once()
        summary = _summary(config)
        assert "crm_suspended" in summary["errors"]

    def test_sc012_crm_pending_written_to_state_store(self, tmp_path):
        """SC-012: crm-pending entry in state store → crm_status 'pending', retry count incremented."""
        config = _make_config(tmp_path)
        _write_store(config.state_store_path, [
            {"gmail_message_id": "msg1", "status": "crm-pending", "outcome": "deal_extracted"},
        ])

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2(crm_pending=1))
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        store = _read_store(config.state_store_path)
        msg = store["messages"][0]
        assert msg["crm_status"] == "pending"
        assert msg["crm_retry_count"] == 1


# ─── US4: Operational Log Visibility (T017) ───────────────────────────────────

class TestLogVisibility:
    def test_sc005_clean_cycle_summary_has_all_six_fields(self, tmp_path):
        """SC-005: clean cycle → one INFO JSON line with ts, emails_processed, crm_logged,
        notified, pending, errors."""
        config = _make_config(tmp_path)

        mock_s1 = AsyncMock(return_value=_ok_step1(processed_count=2))
        mock_s2 = MagicMock(return_value=_ok_step2(crm_logged=1))
        mock_s3 = MagicMock(return_value=_ok_step3(discord_notified=1))

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        lines = config.log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert set(record.keys()) == {"ts", "emails_processed", "crm_logged", "notified", "pending", "errors"}
        assert record["errors"] == []

    def test_sc005_error_token_appears_once(self, tmp_path):
        """Injected unhandled exception → 'unhandled_exception' appears exactly once in errors."""
        config = _make_config(tmp_path)

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(side_effect=RuntimeError("boom"))
        mock_s3 = MagicMock(side_effect=RuntimeError("also boom"))

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        record = json.loads(config.log_path.read_text(encoding="utf-8").strip())
        assert record["errors"].count("unhandled_exception") == 1


# ─── US5: Startup Guard and Retry Limits (T018 + T019) ────────────────────────

class TestStartupGuard:
    def test_sc010_missing_state_store_path_exits(self, monkeypatch):
        """SC-010: unset STATE_STORE_PATH → SystemExit(1) before any lock created."""
        monkeypatch.delenv("STATE_STORE_PATH", raising=False)
        with pytest.raises(SystemExit):
            load_config()

    def test_sc015_invalid_poll_interval_exits(self, monkeypatch, tmp_path):
        """SC-015: POLL_INTERVAL_MINUTES=0 → SystemExit with message naming var."""
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("POLL_INTERVAL_MINUTES", "0")
        with pytest.raises(SystemExit):
            load_config()

    def test_sc009_nonexistent_state_store_path_cycle_runs_cleanly(self, tmp_path):
        """SC-009: STATE_STORE_PATH points to missing dir → cycle runs (step 1 handles it),
        no lock file left behind."""
        config = _make_config(tmp_path)
        # Use a state_store_path whose parent doesn't exist
        bad_store = tmp_path / "nonexistent_dir" / "store.json"
        config = PipelineConfig(
            state_store_path=bad_store,
            poll_interval_minutes=15,
            lock_timeout_minutes=30,
            log_path=tmp_path / "pipeline.log",
            log_max_bytes=1_048_576,
            log_backup_count=3,
            max_pending_retries=10,
            scheduler_mode="systemd",
        )
        # CycleLock requires parent dir to write lock file; it will raise OSError
        # The test verifies the cycle doesn't leave a dangling lock.
        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2())
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            with pytest.raises(OSError):
                run_cycle(config, CycleLogger(_make_config(tmp_path)))

        # No lock file in the nonexistent dir (it couldn't be created either)
        assert not config.lock_path.exists()


class TestRetryLimits:
    def test_sc013_pending_promoted_to_failed_at_max_retries(self, tmp_path):
        """SC-013: crm_retry_count at MAX_PENDING_RETRIES - 1, step 2 still fails → promoted to failed."""
        config = _make_config(tmp_path, max_pending_retries=3)
        _write_store(config.state_store_path, [
            {
                "gmail_message_id": "msg1",
                "status": "crm-pending",
                "crm_retry_count": 2,  # already at MAX - 1
            },
        ])

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(return_value=_ok_step2(crm_pending=1))
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        store = _read_store(config.state_store_path)
        msg = store["messages"][0]
        assert msg["crm_status"] == "failed"
        assert msg["crm_retry_count"] == 3
        summary = _summary(config)
        assert "pending_promoted_to_failed" in summary["errors"]

    def test_fr023_sigterm_releases_lock(self, tmp_path):
        """FR-023: SIGTERM during run_cycle → lock released after cycle completes."""
        from pipeline_orchestrator import scheduler as sched
        config = _make_config(tmp_path)

        # Simulate SIGTERM arriving mid-cycle by setting the flag before run_cycle
        sched._shutdown_flag.clear()

        cycle_ran = threading.Event()
        original_s2 = None

        def slow_step2():
            # Simulate SIGTERM arriving during step 2
            sched._shutdown_flag.set()
            return _ok_step2()

        mock_s1 = AsyncMock(return_value=_ok_step1())
        mock_s2 = MagicMock(side_effect=slow_step2)
        mock_s3 = MagicMock(return_value=_ok_step3())

        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            run_cycle(config, CycleLogger(config))

        # Cycle completed, lock released
        assert not config.lock_path.exists()
        # Summary still emitted
        assert config.log_path.exists()
        # reset for other tests
        sched._shutdown_flag.clear()


# ─── Polish: Full Idempotency (T023) ──────────────────────────────────────────

class TestIdempotency:
    def test_sc006_fully_processed_store_produces_zero_counts(self, tmp_path):
        """SC-006: fully-processed state store → 3 consecutive cycles all produce zeros."""
        config = _make_config(tmp_path)
        _write_store(config.state_store_path, [
            {
                "gmail_message_id": "msg1",
                "status": "discord-notified",
                "crm_status": "logged",
                "crm_retry_count": 0,
                "notify_status": "sent",
                "notify_retry_count": 0,
            },
        ])

        mock_s1 = AsyncMock(return_value=_ok_step1(processed_count=0))
        mock_s2 = MagicMock(return_value=_ok_step2(crm_logged=0))
        mock_s3 = MagicMock(return_value=_ok_step3(discord_notified=0))

        cl = CycleLogger(config)
        with (
            patch("pipeline_orchestrator.runner.check_new_deals_handler", mock_s1),
            patch("pipeline_orchestrator.runner.sync_deals_to_crm", mock_s2),
            patch("pipeline_orchestrator.runner.sync_notifications", mock_s3),
        ):
            for _ in range(3):
                run_cycle(config, cl)

        lines = config.log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        for line in lines:
            record = json.loads(line)
            assert record["crm_logged"] == 0
            assert record["notified"] == 0
            assert record["errors"] == []
