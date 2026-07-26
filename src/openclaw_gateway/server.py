"""OpenClaw gateway — FastMCP server instance and MCP tool registrations."""
from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP("openclaw-gateway")

# Runtime state — set by __main__.py at startup
_gateway_start_time: float = 0.0
_last_cycle_at: Optional[str] = None
_cycle_running: bool = False
_config: Optional[object] = None  # GatewayConfig; lazy type to avoid top-level circular import


@mcp.tool()
def get_gateway_status() -> dict:
    import openclaw_gateway.server as _srv
    from openclaw_gateway.tools.status import get_gateway_status as _impl
    return _impl(_srv._config)


@mcp.tool()
def get_health() -> dict:
    import openclaw_gateway.server as _srv
    from openclaw_gateway.tools.status import get_health as _impl
    return _impl(_srv._config)


@mcp.tool()
def run_cycle() -> dict:
    from openclaw_gateway.tools.pipeline import run_cycle as _impl
    return _impl()


@mcp.tool()
def get_pipeline_cycles(limit: int = 20) -> dict:
    from openclaw_gateway.tools.pipeline import get_pipeline_cycles as _impl
    return _impl(limit=limit)


@mcp.tool()
def get_deals(limit: int = 50, status: str = "all") -> dict:
    from openclaw_gateway.tools.pipeline import get_deals as _impl
    return _impl(limit=limit, status=status)


@mcp.tool()
def get_quota_usage() -> dict:
    from openclaw_gateway.tools.pipeline import get_quota_usage as _impl
    return _impl()


# Dashboard REST endpoints — thin HTTP adapter over the MCP tool implementations
from openclaw_gateway.routes.api import (  # noqa: E402
    serve_dashboard,
    api_status,
    api_cycles,
    api_deals,
    api_quota,
    api_run_cycle,
)
from openclaw_gateway.routes.email_api import (  # noqa: E402
    api_approve_email,
    api_cancel_email,
    api_list_emails,
    api_list_email_events,
)

mcp.custom_route("/", methods=["GET"])(serve_dashboard)
mcp.custom_route("/api/status", methods=["GET"])(api_status)
mcp.custom_route("/api/cycles", methods=["GET"])(api_cycles)
mcp.custom_route("/api/deals", methods=["GET"])(api_deals)
mcp.custom_route("/api/quota", methods=["GET"])(api_quota)
mcp.custom_route("/api/run-cycle", methods=["POST"])(api_run_cycle)
mcp.custom_route("/api/emails", methods=["GET"])(api_list_emails)
mcp.custom_route("/api/emails/{email_id}/approve", methods=["POST"])(api_approve_email)
mcp.custom_route("/api/emails/{email_id}/cancel", methods=["POST"])(api_cancel_email)
mcp.custom_route("/api/email-events", methods=["GET"])(api_list_email_events)
