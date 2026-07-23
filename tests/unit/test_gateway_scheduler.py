"""Tests for openclaw_gateway.scheduler.SchedulerThread."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import openclaw_gateway.scheduler as scheduler_mod
from openclaw_gateway.scheduler import SchedulerThread


def _make_cfg(tmp_path):
    return SimpleNamespace(
        poll_interval_minutes=1,
        log_path=tmp_path / "pipeline.log",
        log_max_bytes=1_048_576,
        log_backup_count=3,
    )


class TestSchedulerThread:

    def test_daemon_true(self, tmp_path):
        sched = SchedulerThread(_make_cfg(tmp_path))
        assert sched.daemon is True

    def test_start_stop_no_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scheduler_mod, "_run_one_cycle", lambda cfg, lg: None)
        sched = SchedulerThread(_make_cfg(tmp_path), interval_seconds=100)
        sched.start()
        time.sleep(0.05)
        sched.stop()
        sched.join(timeout=1.5)
        assert not sched.is_alive()

    def test_run_cycle_called_at_least_once(self, tmp_path, monkeypatch):
        call_count = []

        def counting_run(cfg, lg):
            call_count.append(1)

        monkeypatch.setattr(scheduler_mod, "_run_one_cycle", counting_run)
        sched = SchedulerThread(_make_cfg(tmp_path), interval_seconds=0.01)
        sched.start()
        time.sleep(0.2)
        sched.stop()
        sched.join(timeout=1.5)
        assert len(call_count) >= 1

    def test_stop_exits_loop_cleanly(self, tmp_path, monkeypatch):
        call_count = []

        def noop_run(cfg, lg):
            call_count.append(1)

        monkeypatch.setattr(scheduler_mod, "_run_one_cycle", noop_run)
        sched = SchedulerThread(_make_cfg(tmp_path), interval_seconds=100)
        sched.start()
        time.sleep(0.05)
        before = len(call_count)
        sched.stop()
        sched.join(timeout=2.0)
        assert not sched.is_alive()
        after = len(call_count)
        assert after - before <= 1
