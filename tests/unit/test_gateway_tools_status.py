"""Tests for get_health(), _check_state_store(), and get_gateway_status()."""
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import openclaw_gateway.server as _srv_mod
import openclaw_gateway.tools.status as status_mod
from openclaw_gateway.tools.status import _check_state_store, get_gateway_status, get_health

# ── helpers ────────────────────────────────────────────────────────────────────

def _pass(name, latency_ms=100):
    return {"name": name, "status": "PASS", "latency_ms": latency_ms, "message": None}


def _fail(name, message="error"):
    return {"name": name, "status": "FAIL", "latency_ms": None, "message": message}


def _all_pass_components():
    return [
        _pass("gmail_oauth", 820),
        _pass("gemini_api", 450),
        _pass("hubspot_token", 310),
        _pass("discord_webhook", 180),
        {"name": "state_store", "status": "PASS", "latency_ms": None, "message": None},
    ]


def _mock_config():
    cfg = MagicMock()
    cfg.state_store_path = Path("/tmp/nonexistent.json")
    return cfg


def _patch_all_checks(components):
    return (
        patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
        patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
        patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
        patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
        patch.object(status_mod, "_check_state_store", return_value=components[4]),
    )


# ── get_health() aggregation ───────────────────────────────────────────────────

class TestGetHealthAggregation:

    def test_all_pass_returns_healthy(self):
        components = _all_pass_components()
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        assert report["overall"] == "HEALTHY"

    def test_all_pass_has_five_components(self):
        components = _all_pass_components()
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        assert len(report["components"]) == 5

    def test_one_fail_returns_degraded(self):
        components = _all_pass_components()
        components[4] = _fail("state_store", "File not found: /tmp/x.json")
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        assert report["overall"] == "DEGRADED"

    def test_gmail_fail_returns_degraded(self):
        components = _all_pass_components()
        components[0] = _fail("gmail_oauth", "Token refresh failed: invalid_grant")
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        assert report["overall"] == "DEGRADED"

    def test_failed_component_status_preserved(self):
        components = _all_pass_components()
        components[4] = _fail("state_store", "File not found")
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        state_comp = next(c for c in report["components"] if c["name"] == "state_store")
        assert state_comp["status"] == "FAIL"
        assert "not found" in state_comp["message"].lower() or "File not found" in state_comp["message"]

    def test_component_schema_has_required_keys(self):
        components = _all_pass_components()
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        for comp in report["components"]:
            assert "name" in comp
            assert "status" in comp
            assert "latency_ms" in comp
            assert "message" in comp

    def test_report_has_checked_at(self):
        components = _all_pass_components()
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        assert "checked_at" in report
        assert "T" in report["checked_at"]  # ISO-8601 UTC

    def test_report_duration_ms_is_non_negative_int(self):
        components = _all_pass_components()
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        assert isinstance(report["duration_ms"], int)
        assert report["duration_ms"] >= 0

    def test_component_names_match_spec(self):
        components = _all_pass_components()
        with (
            patch.object(status_mod, "_check_gmail_oauth", return_value=components[0]),
            patch.object(status_mod, "_check_gemini_api", return_value=components[1]),
            patch.object(status_mod, "_check_hubspot_token", return_value=components[2]),
            patch.object(status_mod, "_check_discord_webhook", return_value=components[3]),
            patch.object(status_mod, "_check_state_store", return_value=components[4]),
        ):
            report = get_health(_mock_config())
        names = [c["name"] for c in report["components"]]
        assert names == ["gmail_oauth", "gemini_api", "hubspot_token", "discord_webhook", "state_store"]


# ── _check_state_store() unit tests (no mocking — uses real files) ─────────────

class TestCheckStateStore:

    def test_pass_with_valid_json_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"messages": []}), encoding="utf-8")
        result = _check_state_store(state_file)
        assert result["status"] == "PASS"
        assert result["name"] == "state_store"
        assert result["message"] is None

    def test_fail_when_file_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = _check_state_store(missing)
        assert result["status"] == "FAIL"
        assert result["message"] is not None
        assert "not found" in result["message"].lower() or "File not found" in result["message"]

    def test_fail_when_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("NOT JSON {{{", encoding="utf-8")
        result = _check_state_store(bad_file)
        assert result["status"] == "FAIL"
        assert result["message"] is not None

    def test_latency_ms_is_none_for_local_check(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text("{}", encoding="utf-8")
        result = _check_state_store(state_file)
        assert result["latency_ms"] is None

    def test_component_name_is_state_store(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text("{}", encoding="utf-8")
        result = _check_state_store(state_file)
        assert result["name"] == "state_store"


# ── T013: get_gateway_status() ─────────────────────────────────────────────────

class TestGetGatewayStatus:

    def _cfg(self):
        cfg = MagicMock()
        cfg.gateway_host = "127.0.0.1"
        cfg.gateway_port = 18790
        return cfg

    def test_has_all_required_keys(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_gateway_start_time", time.time() - 60)
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", None)
        monkeypatch.setattr(_srv_mod, "_cycle_running", False)
        result = get_gateway_status(self._cfg())
        for key in ("running", "uptime_seconds", "version", "host", "port", "last_cycle_at", "cycle_running"):
            assert key in result, f"Missing key: {key}"

    def test_running_is_always_true(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_gateway_start_time", time.time() - 60)
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", None)
        monkeypatch.setattr(_srv_mod, "_cycle_running", False)
        result = get_gateway_status(self._cfg())
        assert result["running"] is True

    def test_version_matches_package_version(self, monkeypatch):
        from openclaw_gateway import __version__
        monkeypatch.setattr(_srv_mod, "_gateway_start_time", time.time() - 60)
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", None)
        monkeypatch.setattr(_srv_mod, "_cycle_running", False)
        result = get_gateway_status(self._cfg())
        assert result["version"] == __version__

    def test_uptime_seconds_is_non_negative_int(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_gateway_start_time", time.time() - 60)
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", None)
        monkeypatch.setattr(_srv_mod, "_cycle_running", False)
        result = get_gateway_status(self._cfg())
        assert isinstance(result["uptime_seconds"], int)
        assert result["uptime_seconds"] >= 0

    def test_host_and_port_from_config(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_gateway_start_time", time.time())
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", None)
        monkeypatch.setattr(_srv_mod, "_cycle_running", False)
        result = get_gateway_status(self._cfg())
        assert result["host"] == "127.0.0.1"
        assert result["port"] == 18790

    def test_last_cycle_at_is_never_when_none(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_gateway_start_time", time.time())
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", None)
        monkeypatch.setattr(_srv_mod, "_cycle_running", False)
        result = get_gateway_status(self._cfg())
        assert result["last_cycle_at"] == "never"

    def test_last_cycle_at_reflected_when_set(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_gateway_start_time", time.time())
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", "2026-07-23T12:00:00Z")
        monkeypatch.setattr(_srv_mod, "_cycle_running", False)
        result = get_gateway_status(self._cfg())
        assert result["last_cycle_at"] == "2026-07-23T12:00:00Z"

    def test_cycle_running_reflected(self, monkeypatch):
        monkeypatch.setattr(_srv_mod, "_gateway_start_time", time.time())
        monkeypatch.setattr(_srv_mod, "_last_cycle_at", None)
        monkeypatch.setattr(_srv_mod, "_cycle_running", True)
        result = get_gateway_status(self._cfg())
        assert result["cycle_running"] is True
