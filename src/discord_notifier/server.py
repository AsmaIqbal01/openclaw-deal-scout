"""Discord Notifier — FastMCP server exposing the sync_notifications tool."""

import dataclasses
import logging
import os

from fastmcp import FastMCP

from discord_notifier.models import NotificationCycleResult
from discord_notifier.orchestrator import run_notify_cycle

logger = logging.getLogger(__name__)

mcp = FastMCP("discord-notifier")


@mcp.tool()
def sync_notifications() -> dict:
    """Deliver pending Discord notifications for deals logged in the state store.

    Reads NOTIFIER, DISCORD_WEBHOOK_URL (when NOTIFIER=discord), and
    STATE_STORE_PATH from the environment. Calls run_notify_cycle() and
    returns a NotificationCycleResult dict.

    On any unhandled exception the tool returns status='error' with
    error_details set — it never propagates an exception to the MCP caller.
    """
    state_path = os.environ.get("STATE_STORE_PATH", "processed_ids.json")
    env = dict(os.environ)

    try:
        result: NotificationCycleResult = run_notify_cycle(state_path, env=env)
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_notifications: unhandled exception in run_notify_cycle")
        return dataclasses.asdict(
            NotificationCycleResult(
                status="error",
                error_details=f"{type(exc).__name__}: {exc}",
            )
        )

    return dataclasses.asdict(result)


if __name__ == "__main__":
    mcp.run()
