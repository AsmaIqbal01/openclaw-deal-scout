"""Unit tests for openclaw_gateway.routes.api REST handlers."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from openclaw_gateway.routes.api import (
    api_cycles,
    api_deals,
    api_quota,
    api_run_cycle,
    api_status,
    serve_dashboard,
)


class _Req:
    """Minimal Starlette Request stand-in for unit tests."""

    def __init__(self, params: dict | None = None):
        self.query_params = params or {}


# ── serve_dashboard ──────────────────────────────────────────────────────────


async def test_serve_dashboard_returns_html():
    with patch("openclaw_gateway.routes.api.pkg_resources") as mock_pkg:
        mock_pkg.files.return_value.joinpath.return_value.read_text.return_value = (
            "<html><body>OpenClaw Dashboard</body></html>"
        )
        resp = await serve_dashboard(_Req())
    assert resp.status_code == 200
    assert b"OpenClaw Dashboard" in resp.body


async def test_serve_dashboard_content_type():
    with patch("openclaw_gateway.routes.api.pkg_resources") as mock_pkg:
        mock_pkg.files.return_value.joinpath.return_value.read_text.return_value = "<html></html>"
        resp = await serve_dashboard(_Req())
    assert "text/html" in resp.headers["content-type"]


async def test_serve_dashboard_500_on_read_error():
    with patch("openclaw_gateway.routes.api.pkg_resources") as mock_pkg:
        mock_pkg.files.return_value.joinpath.return_value.read_text.side_effect = FileNotFoundError(
            "dashboard.html not found"
        )
        resp = await serve_dashboard(_Req())
    assert resp.status_code == 500
    assert b"dashboard.html" in resp.body


# ── api_status ───────────────────────────────────────────────────────────────


async def test_api_status_returns_gateway_and_health():
    fake_gw = {"running": True, "uptime_seconds": 100, "cycle_running": False}
    fake_health = {"overall": "HEALTHY", "components": [], "checked_at": "2026-07-24T00:00:00Z"}
    with (
        patch("openclaw_gateway.routes.api.pkg_resources"),
        patch("openclaw_gateway.server._config", MagicMock()),
        patch("openclaw_gateway.tools.status.get_gateway_status", return_value=fake_gw),
        patch("openclaw_gateway.tools.status.get_health", return_value=fake_health),
    ):
        resp = await api_status(_Req())
    assert resp.status_code == 200
    import json
    body = json.loads(resp.body)
    assert body["gateway"] == fake_gw
    assert body["health"] == fake_health


async def test_api_status_cors_header():
    with (
        patch("openclaw_gateway.server._config", MagicMock()),
        patch("openclaw_gateway.tools.status.get_gateway_status", return_value={}),
        patch("openclaw_gateway.tools.status.get_health", return_value={}),
    ):
        resp = await api_status(_Req())
    assert resp.headers.get("access-control-allow-origin") == "*"


async def test_api_status_500_on_exception():
    with patch("openclaw_gateway.routes.api.pkg_resources"):
        with patch(
            "openclaw_gateway.tools.status.get_gateway_status",
            side_effect=RuntimeError("boom"),
        ):
            resp = await api_status(_Req())
    import json
    body = json.loads(resp.body)
    assert resp.status_code == 500
    assert "error" in body
    assert body["endpoint"] == "/api/status"


# ── api_cycles ───────────────────────────────────────────────────────────────


async def test_api_cycles_default_limit():
    fake = {"cycles": [], "total_in_log": 0}
    with patch("openclaw_gateway.tools.pipeline.get_pipeline_cycles", return_value=fake) as mock_fn:
        resp = await api_cycles(_Req())
    mock_fn.assert_called_once_with(limit=20)
    assert resp.status_code == 200


async def test_api_cycles_custom_limit():
    fake = {"cycles": [], "total_in_log": 5}
    with patch("openclaw_gateway.tools.pipeline.get_pipeline_cycles", return_value=fake) as mock_fn:
        resp = await api_cycles(_Req({"limit": "5"}))
    mock_fn.assert_called_once_with(limit=5)


async def test_api_cycles_clamps_limit_to_100():
    fake = {"cycles": [], "total_in_log": 0}
    with patch("openclaw_gateway.tools.pipeline.get_pipeline_cycles", return_value=fake) as mock_fn:
        await api_cycles(_Req({"limit": "999"}))
    mock_fn.assert_called_once_with(limit=100)


async def test_api_cycles_invalid_limit_uses_default():
    fake = {"cycles": [], "total_in_log": 0}
    with patch("openclaw_gateway.tools.pipeline.get_pipeline_cycles", return_value=fake) as mock_fn:
        await api_cycles(_Req({"limit": "not-a-number"}))
    mock_fn.assert_called_once_with(limit=20)


async def test_api_cycles_cors_header():
    with patch("openclaw_gateway.tools.pipeline.get_pipeline_cycles", return_value={"cycles": [], "total_in_log": 0}):
        resp = await api_cycles(_Req())
    assert resp.headers.get("access-control-allow-origin") == "*"


# ── api_deals ────────────────────────────────────────────────────────────────


async def test_api_deals_default_params():
    fake = {"deals": [], "total_deals": 0, "filtered_by": "all"}
    with patch("openclaw_gateway.tools.pipeline.get_deals", return_value=fake) as mock_fn:
        resp = await api_deals(_Req())
    mock_fn.assert_called_once_with(limit=50, status="all")
    assert resp.status_code == 200


async def test_api_deals_valid_status():
    fake = {"deals": [], "total_deals": 0, "filtered_by": "crm_pending"}
    with patch("openclaw_gateway.tools.pipeline.get_deals", return_value=fake) as mock_fn:
        resp = await api_deals(_Req({"status": "crm_pending"}))
    mock_fn.assert_called_once_with(limit=50, status="crm_pending")
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "status",
    ["all", "crm_pending", "crm_failed", "notify_pending", "notify_failed", "complete"],
)
async def test_api_deals_all_valid_statuses_accepted(status):
    fake = {"deals": [], "total_deals": 0, "filtered_by": status}
    with patch("openclaw_gateway.tools.pipeline.get_deals", return_value=fake):
        resp = await api_deals(_Req({"status": status}))
    assert resp.status_code == 200


async def test_api_deals_invalid_status_returns_400():
    resp = await api_deals(_Req({"status": "bogus"}))
    assert resp.status_code == 400
    import json
    body = json.loads(resp.body)
    assert "error" in body
    assert "bogus" in body["error"]


async def test_api_deals_clamps_limit_to_500():
    fake = {"deals": [], "total_deals": 0, "filtered_by": "all"}
    with patch("openclaw_gateway.tools.pipeline.get_deals", return_value=fake) as mock_fn:
        await api_deals(_Req({"limit": "9999"}))
    mock_fn.assert_called_once_with(limit=500, status="all")


async def test_api_deals_cors_header():
    with patch("openclaw_gateway.tools.pipeline.get_deals", return_value={"deals": [], "total_deals": 0, "filtered_by": "all"}):
        resp = await api_deals(_Req())
    assert resp.headers.get("access-control-allow-origin") == "*"


# ── api_quota ────────────────────────────────────────────────────────────────


async def test_api_quota_returns_quota_dict():
    fake = {
        "estimated_requests_today": 42,
        "daily_free_tier_limit": 1500,
        "estimated_remaining": 1458,
        "pct_used": 2.8,
        "window_date": "2026-07-24",
        "cycles_today": 3,
        "has_quota_error_today": False,
    }
    with patch("openclaw_gateway.tools.pipeline.get_quota_usage", return_value=fake):
        resp = await api_quota(_Req())
    import json
    assert resp.status_code == 200
    assert json.loads(resp.body) == fake


async def test_api_quota_cors_header():
    with patch("openclaw_gateway.tools.pipeline.get_quota_usage", return_value={}):
        resp = await api_quota(_Req())
    assert resp.headers.get("access-control-allow-origin") == "*"


async def test_api_quota_500_on_exception():
    with patch("openclaw_gateway.tools.pipeline.get_quota_usage", side_effect=OSError("no log")):
        resp = await api_quota(_Req())
    import json
    body = json.loads(resp.body)
    assert resp.status_code == 500
    assert body["endpoint"] == "/api/quota"


# ── api_run_cycle ─────────────────────────────────────────────────────────────


async def test_api_run_cycle_success():
    fake = {"ts": "2026-07-24T10:00:00Z", "emails_processed": 3, "crm_logged": 1, "notified": 1, "pending": 0, "errors": []}
    with patch("openclaw_gateway.tools.pipeline.run_cycle", return_value=fake):
        resp = await api_run_cycle(_Req())
    import json
    assert resp.status_code == 200
    assert json.loads(resp.body) == fake


async def test_api_run_cycle_busy():
    fake = {"busy": True, "message": "A pipeline cycle is already running."}
    with patch("openclaw_gateway.tools.pipeline.run_cycle", return_value=fake):
        resp = await api_run_cycle(_Req())
    import json
    body = json.loads(resp.body)
    assert resp.status_code == 200
    assert body["busy"] is True


async def test_api_run_cycle_error_dict():
    fake = {"error": "Connection refused", "ts": "2026-07-24T10:00:00Z"}
    with patch("openclaw_gateway.tools.pipeline.run_cycle", return_value=fake):
        resp = await api_run_cycle(_Req())
    import json
    body = json.loads(resp.body)
    assert "error" in body


async def test_api_run_cycle_cors_header():
    with patch("openclaw_gateway.tools.pipeline.run_cycle", return_value={}):
        resp = await api_run_cycle(_Req())
    assert resp.headers.get("access-control-allow-origin") == "*"


async def test_api_run_cycle_unexpected_exception():
    with patch("openclaw_gateway.tools.pipeline.run_cycle", side_effect=RuntimeError("unexpected")):
        resp = await api_run_cycle(_Req())
    import json
    body = json.loads(resp.body)
    assert resp.status_code == 200
    assert "error" in body
    assert "ts" in body
