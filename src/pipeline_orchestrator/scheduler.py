"""pipeline_orchestrator.scheduler — sleep-loop mode for dev/test."""
from __future__ import annotations

import logging
import threading

from pipeline_orchestrator.config import PipelineConfig
from pipeline_orchestrator.cycle_logger import CycleLogger
from pipeline_orchestrator.lock import CycleLockActiveError
from pipeline_orchestrator.runner import run_cycle

logger = logging.getLogger(__name__)

# Set by the SIGTERM handler in __main__.py; wakes the wait() immediately.
_shutdown_flag = threading.Event()


def run_loop(config: PipelineConfig, cycle_logger: CycleLogger) -> None:
    """Run pipeline cycles in a sleep loop until SIGTERM sets _shutdown_flag."""
    logger.info("scheduler: loop mode started (interval=%d min)", config.poll_interval_minutes)
    while not _shutdown_flag.is_set():
        try:
            run_cycle(config, cycle_logger)
        except CycleLockActiveError:
            logger.warning("scheduler: concurrent cycle detected — skipping this tick")
        # Wait for the next interval, but wake immediately on SIGTERM.
        _shutdown_flag.wait(timeout=config.poll_interval_minutes * 60)
    logger.info("scheduler: shutdown flag set — exiting loop")
