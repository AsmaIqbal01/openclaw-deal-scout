"""CRM Logger — FastMCP server exposing the sync_deals_to_crm tool."""

import dataclasses
import logging
import os

from fastmcp import FastMCP

from crm_logger.models import CrmCycleResult
from crm_logger.orchestrator import run_crm_cycle

logger = logging.getLogger(__name__)

mcp = FastMCP("crm-logger")


@mcp.tool()
def sync_deals_to_crm() -> dict:
    """Sync confirmed deal entries from the state store to HubSpot CRM.

    Reads HUBSPOT_PRIVATE_APP_TOKEN and STATE_STORE_PATH from the environment.
    Calls run_crm_cycle() and returns a CrmCycleResult dict.

    On any unhandled exception the tool returns status='error' with
    error_details set — it never propagates an exception to the MCP caller.
    """
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")
    state_path = os.environ.get("STATE_STORE_PATH", "processed_ids.json")

    if not token:
        logger.error("sync_deals_to_crm: HUBSPOT_PRIVATE_APP_TOKEN not set")
        return dataclasses.asdict(
            CrmCycleResult(
                status="error",
                error_details="HUBSPOT_PRIVATE_APP_TOKEN environment variable not set",
            )
        )

    try:
        result: CrmCycleResult = run_crm_cycle(state_path, token)
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_deals_to_crm: unhandled exception in run_crm_cycle")
        return dataclasses.asdict(
            CrmCycleResult(
                status="error",
                error_details=f"{type(exc).__name__}: {exc}",
            )
        )

    return dataclasses.asdict(result)


if __name__ == "__main__":
    mcp.run()
