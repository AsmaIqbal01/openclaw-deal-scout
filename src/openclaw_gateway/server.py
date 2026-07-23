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
