"""SchedulerThread — background thread that runs pipeline cycles on an interval."""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


def _run_one_cycle(config, cycle_logger) -> None:
    """Run a single pipeline cycle. Isolated function so tests can patch it."""
    import pipeline_orchestrator.runner as _runner
    _runner.run_cycle(config, cycle_logger)


class SchedulerThread(threading.Thread):
    """Daemon thread that calls _run_one_cycle on a configurable interval.

    Args:
        config: GatewayConfig (or any object with poll_interval_minutes).
        interval_seconds: Override the cycle interval in seconds. Defaults to
            config.poll_interval_minutes * 60.
    """

    def __init__(self, config, interval_seconds: Optional[float] = None) -> None:
        super().__init__(daemon=True, name="openclaw-scheduler")
        self._config = config
        self._interval = (
            interval_seconds
            if interval_seconds is not None
            else config.poll_interval_minutes * 60
        )
        self._stop_event = threading.Event()

    def run(self) -> None:
        from pipeline_orchestrator.cycle_logger import CycleLogger
        cycle_logger = CycleLogger(self._config)
        while not self._stop_event.is_set():
            try:
                _run_one_cycle(self._config, cycle_logger)
            except Exception:
                logger.exception("scheduler: unhandled exception in pipeline cycle")
            self._stop_event.wait(self._interval)

    def stop(self) -> None:
        """Signal the scheduler to stop after the current cycle completes."""
        self._stop_event.set()
