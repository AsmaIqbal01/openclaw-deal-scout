"""Tests for the openclaw CLI — doctor subcommand."""
import sys
from unittest.mock import MagicMock, patch

import pytest

import openclaw_gateway.cli as cli_mod

# ── fixture reports ────────────────────────────────────────────────────────────

_HEALTHY_REPORT = {
    "overall": "HEALTHY",
    "checked_at": "2026-07-23T12:00:00Z",
    "duration_ms": 1760,
    "components": [
        {"name": "gmail_oauth", "status": "PASS", "latency_ms": 820, "message": None},
        {"name": "gemini_api", "status": "PASS", "latency_ms": 450, "message": None},
        {"name": "hubspot_token", "status": "PASS", "latency_ms": 310, "message": None},
        {"name": "discord_webhook", "status": "PASS", "latency_ms": 180, "message": None},
        {"name": "state_store", "status": "PASS", "latency_ms": None, "message": None},
    ],
}

_DEGRADED_REPORT = {
    "overall": "DEGRADED",
    "checked_at": "2026-07-23T12:00:00Z",
    "duration_ms": 500,
    "components": [
        {
            "name": "gmail_oauth",
            "status": "FAIL",
            "latency_ms": None,
            "message": "Token refresh failed: invalid_grant. Re-run setup_oauth.py.",
        },
        {"name": "gemini_api", "status": "PASS", "latency_ms": 450, "message": None},
        {"name": "hubspot_token", "status": "PASS", "latency_ms": 310, "message": None},
        {"name": "discord_webhook", "status": "PASS", "latency_ms": 180, "message": None},
        {"name": "state_store", "status": "PASS", "latency_ms": None, "message": None},
    ],
}


# ── doctor subcommand ──────────────────────────────────────────────────────────

class TestDoctorCommand:

    def test_exit_0_when_healthy(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "doctor"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=MagicMock()),
            patch.object(cli_mod, "get_health", return_value=_HEALTHY_REPORT),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_mod.main()
        assert exc_info.value.code == 0

    def test_exit_1_when_degraded(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "doctor"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=MagicMock()),
            patch.object(cli_mod, "get_health", return_value=_DEGRADED_REPORT),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_mod.main()
        assert exc_info.value.code == 1

    def test_stdout_contains_all_component_names(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "doctor"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=MagicMock()),
            patch.object(cli_mod, "get_health", return_value=_HEALTHY_REPORT),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        for name in ("gmail_oauth", "gemini_api", "hubspot_token", "discord_webhook", "state_store"):
            assert name in out

    def test_stdout_contains_healthy_overall(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "doctor"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=MagicMock()),
            patch.object(cli_mod, "get_health", return_value=_HEALTHY_REPORT),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "HEALTHY" in out

    def test_stdout_contains_fail_message_on_degraded(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "doctor"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=MagicMock()),
            patch.object(cli_mod, "get_health", return_value=_DEGRADED_REPORT),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "invalid_grant" in out

    def test_stdout_contains_doctor_header(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "doctor"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=MagicMock()),
            patch.object(cli_mod, "get_health", return_value=_HEALTHY_REPORT),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "Doctor" in out

    def test_stdout_contains_degraded_overall(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "doctor"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=MagicMock()),
            patch.object(cli_mod, "get_health", return_value=_DEGRADED_REPORT),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "DEGRADED" in out

    def test_no_command_exits_nonzero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["openclaw"])
        with pytest.raises(SystemExit) as exc_info:
            cli_mod.main()
        assert exc_info.value.code != 0


# ── T014: gateway status + dashboard ──────────────────────────────────────────

_RUNNING_STATUS = {
    "running": True,
    "uptime_seconds": 3620,
    "version": "0.1.0",
    "host": "127.0.0.1",
    "port": 18790,
    "last_cycle_at": "2026-07-23T00:14:56Z",
    "cycle_running": False,
}


class TestGatewayStatusCommand:

    def _cfg(self):
        cfg = MagicMock()
        cfg.gateway_host = "127.0.0.1"
        cfg.gateway_port = 18790
        return cfg

    def test_exit_0_when_gateway_running(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "gateway", "status"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch.object(cli_mod, "_fetch_gateway_status", return_value=_RUNNING_STATUS),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_mod.main()
        assert exc_info.value.code == 0

    def test_exit_1_when_gateway_stopped(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "gateway", "status"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch.object(cli_mod, "_fetch_gateway_status", return_value=None),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_mod.main()
        assert exc_info.value.code == 1

    def test_stdout_contains_running_when_up(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "gateway", "status"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch.object(cli_mod, "_fetch_gateway_status", return_value=_RUNNING_STATUS),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "RUNNING" in out

    def test_stdout_contains_stopped_when_down(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "gateway", "status"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch.object(cli_mod, "_fetch_gateway_status", return_value=None),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "STOPPED" in out

    def test_stdout_contains_host_and_port(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "gateway", "status"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch.object(cli_mod, "_fetch_gateway_status", return_value=_RUNNING_STATUS),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "127.0.0.1" in out
        assert "18790" in out

    def test_stdout_contains_version(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "gateway", "status"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch.object(cli_mod, "_fetch_gateway_status", return_value=_RUNNING_STATUS),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "0.1.0" in out

    def test_stdout_contains_stopped_host_when_down(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "gateway", "status"])
        cfg = self._cfg()
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=cfg),
            patch.object(cli_mod, "_fetch_gateway_status", return_value=None),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "STOPPED" in out


class TestDashboardCommand:

    def _cfg(self):
        cfg = MagicMock()
        cfg.gateway_host = "127.0.0.1"
        cfg.gateway_port = 18790
        return cfg

    def test_exit_0_on_dashboard(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["openclaw", "dashboard"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch("webbrowser.open"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_mod.main()
        assert exc_info.value.code == 0

    def test_opens_browser_with_gateway_url(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["openclaw", "dashboard"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch("webbrowser.open") as mock_open,
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        mock_open.assert_called_once()
        url = mock_open.call_args[0][0]
        assert "127.0.0.1" in url
        assert "18790" in url

    def test_stdout_contains_url(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["openclaw", "dashboard"])
        with (
            patch.object(cli_mod, "load_gateway_config", return_value=self._cfg()),
            patch("webbrowser.open"),
        ):
            with pytest.raises(SystemExit):
                cli_mod.main()
        out = capsys.readouterr().out
        assert "127.0.0.1:18790" in out
