"""Smoke tests for the dashboard.html package resource."""
from __future__ import annotations

import importlib.resources as pkg_resources


def _html() -> str:
    return (
        pkg_resources.files("openclaw_gateway")
        .joinpath("static/dashboard.html")
        .read_text(encoding="utf-8")
    )


def test_dashboard_html_is_readable():
    assert _html().strip(), "dashboard.html must not be empty"


def test_dashboard_html_contains_title():
    assert "<title>" in _html()


def test_dashboard_html_is_valid_doctype():
    assert _html().strip().lower().startswith("<!doctype html")


def test_dashboard_html_has_status_panel():
    assert 'id="status-panel"' in _html()


def test_dashboard_html_has_cycles_panel():
    assert 'id="cycles-panel"' in _html()


def test_dashboard_html_has_deals_panel():
    assert 'id="deals-panel"' in _html()


def test_dashboard_html_has_quota_panel():
    assert 'id="quota-panel"' in _html()


def test_dashboard_html_has_run_cycle_btn():
    assert 'id="run-cycle-btn"' in _html()


def test_dashboard_html_has_offline_banner():
    assert 'id="offline-banner"' in _html()


def test_dashboard_html_has_deal_filter():
    assert 'id="deal-filter"' in _html()


def test_dashboard_html_no_external_resources():
    html = _html()
    for pattern in ["cdn.", "googleapis.com", "unpkg.com", "jsdelivr.net", "cloudflare.com"]:
        assert pattern not in html, f"External resource detected: {pattern}"


def test_dashboard_html_no_claude_reference():
    html = _html().lower()
    assert "claude" not in html
    assert "anthropic" not in html
