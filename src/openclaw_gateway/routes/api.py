"""REST handlers for the OpenClaw dashboard (/api/* and / endpoints)."""
from __future__ import annotations

import asyncio
import importlib.resources as pkg_resources
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

_VALID_DEAL_STATUSES = frozenset(
    {"all", "crm_pending", "crm_failed", "notify_pending", "notify_failed", "complete"}
)


def _json_response(data: dict, status: int = 200) -> JSONResponse:
    resp = JSONResponse(data, status_code=status)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


def _error(msg: str, endpoint: str) -> JSONResponse:
    return _json_response({"error": msg, "endpoint": endpoint}, status=500)


async def serve_dashboard(request: Request) -> HTMLResponse:
    try:
        html = (
            pkg_resources.files("openclaw_gateway")
            .joinpath("static/dashboard.html")
            .read_text(encoding="utf-8")
        )
        return HTMLResponse(html, status_code=200)
    except Exception as exc:
        return HTMLResponse(
            f"<h1>500 — dashboard.html unavailable</h1><p>{exc}</p>",
            status_code=500,
        )


async def api_status(request: Request) -> JSONResponse:
    try:
        import openclaw_gateway.server as _srv
        from openclaw_gateway.tools.status import get_gateway_status, get_health

        config = _srv._config
        return _json_response({"gateway": get_gateway_status(config), "health": get_health(config)})
    except Exception as exc:
        return _error(str(exc), "/api/status")


async def api_cycles(request: Request) -> JSONResponse:
    try:
        raw = request.query_params.get("limit", "20")
        try:
            limit = max(1, min(100, int(raw)))
        except ValueError:
            limit = 20
        from openclaw_gateway.tools.pipeline import get_pipeline_cycles

        return _json_response(get_pipeline_cycles(limit=limit))
    except Exception as exc:
        return _error(str(exc), "/api/cycles")


async def api_deals(request: Request) -> JSONResponse:
    status = request.query_params.get("status", "all")
    if status not in _VALID_DEAL_STATUSES:
        return JSONResponse(
            {
                "error": (
                    f"Invalid status filter '{status}'. "
                    f"Valid values: {', '.join(sorted(_VALID_DEAL_STATUSES))}"
                )
            },
            status_code=400,
        )
    try:
        raw = request.query_params.get("limit", "50")
        try:
            limit = max(1, min(500, int(raw)))
        except ValueError:
            limit = 50
        from openclaw_gateway.tools.pipeline import get_deals

        return _json_response(get_deals(limit=limit, status=status))
    except Exception as exc:
        return _error(str(exc), "/api/deals")


async def api_quota(request: Request) -> JSONResponse:
    try:
        from openclaw_gateway.tools.pipeline import get_quota_usage

        return _json_response(get_quota_usage())
    except Exception as exc:
        return _error(str(exc), "/api/quota")


async def api_run_cycle(request: Request) -> JSONResponse:
    try:
        from openclaw_gateway.tools.pipeline import run_cycle

        # run_cycle() is synchronous and long-running; offload to a thread so
        # Uvicorn's event loop stays responsive to other requests during the cycle.
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_cycle)
        return _json_response(result)
    except Exception as exc:
        return _json_response(
            {
                "error": str(exc),
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
