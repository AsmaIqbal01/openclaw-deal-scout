"""python -m openclaw_gateway — start the OpenClaw gateway HTTP server."""
from __future__ import annotations

import logging
import signal
import time
from typing import Optional

logger = logging.getLogger(__name__)


def main() -> None:
    from openclaw_gateway.config import load_gateway_config
    from openclaw_gateway import server
    from openclaw_gateway.scheduler import SchedulerThread

    config = load_gateway_config()

    scheduler: Optional[SchedulerThread] = None
    if config.scheduler_mode == "gateway":
        scheduler = SchedulerThread(config)

        def _handle_sigterm(*_: object) -> None:
            logger.info("SIGTERM received — stopping scheduler")
            if scheduler:
                scheduler.stop()

        signal.signal(signal.SIGTERM, _handle_sigterm)
        scheduler.start()
        logger.info(
            "Scheduler started (interval=%ds)", config.poll_interval_minutes * 60
        )

    server._gateway_start_time = time.time()
    server._config = config

    logger.info(
        "Starting OpenClaw gateway on %s:%d", config.gateway_host, config.gateway_port
    )
    server.mcp.run(
        transport="http", host=config.gateway_host, port=config.gateway_port
    )


if __name__ == "__main__":
    main()
