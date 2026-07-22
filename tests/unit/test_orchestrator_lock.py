"""Unit tests for pipeline_orchestrator.lock — T007."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline_orchestrator.lock import CycleLock, CycleLockActiveError, _TIMESTAMP_FMT


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)


def _ts_ago(minutes: int) -> str:
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return t.strftime(_TIMESTAMP_FMT)


class TestCycleLock:
    def test_fresh_lock_created_on_enter(self, tmp_path):
        lock_path = tmp_path / ".pipeline.lock"
        with CycleLock(lock_path, timeout_minutes=30):
            assert lock_path.exists()

    def test_lock_deleted_on_exit(self, tmp_path):
        lock_path = tmp_path / ".pipeline.lock"
        with CycleLock(lock_path, timeout_minutes=30):
            pass
        assert not lock_path.exists()

    def test_lock_contains_utc_timestamp(self, tmp_path):
        lock_path = tmp_path / ".pipeline.lock"
        with CycleLock(lock_path, timeout_minutes=30):
            content = lock_path.read_text(encoding="utf-8").strip()
            # Must parse as UTC ISO-8601 timestamp
            parsed = datetime.strptime(content, _TIMESTAMP_FMT).replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()
            assert 0 <= age_seconds < 5

    def test_active_non_stale_lock_raises(self, tmp_path):
        lock_path = tmp_path / ".pipeline.lock"
        lock_path.write_text(_ts_now(), encoding="utf-8")

        with pytest.raises(CycleLockActiveError):
            CycleLock(lock_path, timeout_minutes=30).__enter__()

        # Existing lock file must be untouched
        assert lock_path.exists()

    def test_stale_lock_is_cleared_and_cycle_proceeds(self, tmp_path):
        lock_path = tmp_path / ".pipeline.lock"
        lock_path.write_text(_ts_ago(35), encoding="utf-8")  # 35 min > 30 min timeout

        with CycleLock(lock_path, timeout_minutes=30):
            assert lock_path.exists()  # new lock created

    def test_malformed_lock_cleared_and_proceeds(self, tmp_path):
        lock_path = tmp_path / ".pipeline.lock"
        lock_path.write_text("NOT_A_TIMESTAMP", encoding="utf-8")

        with CycleLock(lock_path, timeout_minutes=30):
            assert lock_path.exists()  # new lock written

    def test_lock_deleted_even_when_body_raises(self, tmp_path):
        lock_path = tmp_path / ".pipeline.lock"

        with pytest.raises(RuntimeError):
            with CycleLock(lock_path, timeout_minutes=30):
                assert lock_path.exists()
                raise RuntimeError("test error")

        assert not lock_path.exists()

    def test_stale_lock_warn_logged(self, tmp_path, caplog):
        import logging
        lock_path = tmp_path / ".pipeline.lock"
        lock_path.write_text(_ts_ago(35), encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="pipeline_orchestrator.lock"):
            with CycleLock(lock_path, timeout_minutes=30):
                pass

        assert any("stale" in msg.lower() for msg in caplog.messages)

    def test_malformed_lock_warn_logged(self, tmp_path, caplog):
        import logging
        lock_path = tmp_path / ".pipeline.lock"
        lock_path.write_text("GARBAGE", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="pipeline_orchestrator.lock"):
            with CycleLock(lock_path, timeout_minutes=30):
                pass

        assert any("malformed" in msg.lower() for msg in caplog.messages)
