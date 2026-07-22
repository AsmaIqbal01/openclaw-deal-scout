"""Entry point: python -m pipeline_orchestrator."""
from __future__ import annotations

import logging
import signal
import sys
import types

from pipeline_orchestrator import scheduler as _scheduler
from pipeline_orchestrator.config import load_config
from pipeline_orchestrator.cycle_logger import CycleLogger
from pipeline_orchestrator.lock import CycleLockActiveError
from pipeline_orchestrator.runner import run_cycle

logger = logging.getLogger(__name__)


def _sigterm_handler(signum: int, frame: types.FrameType | None) -> None:
    """Allow the current cycle to complete, then exit the loop cleanly (FR-023)."""
    logger.info("SIGTERM received (signal %d) — finishing current cycle then stopping", signum)
    _scheduler._shutdown_flag.set()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    config = load_config()  # exits with code 1 on any validation failure

    # Ensure log directory exists before CycleLogger tries to open the file.
    config.log_path.parent.mkdir(parents=True, exist_ok=True)

    cycle_logger = CycleLogger(config)

    signal.signal(signal.SIGTERM, _sigterm_handler)
    logger.info(
        "pipeline_orchestrator starting (mode=%s, state_store=%s)",
        config.scheduler_mode,
        config.state_store_path,
    )

    if config.scheduler_mode == "systemd":
        try:
            run_cycle(config, cycle_logger)
        except CycleLockActiveError:
            logger.warning("systemd mode: concurrent cycle detected — exiting without running")
            sys.exit(1)
        sys.exit(0)
    else:
        _scheduler.run_loop(config, cycle_logger)


if __name__ == "__main__":
    main()
