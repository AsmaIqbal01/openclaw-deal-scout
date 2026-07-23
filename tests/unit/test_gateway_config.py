"""Tests for GatewayConfig and load_gateway_config()."""
import pytest

from openclaw_gateway.config import GatewayConfig, load_gateway_config

# Minimum env vars required by the underlying PipelineConfig
_BASE_ENV = {"STATE_STORE_PATH": "/tmp/test_state.json", "SCHEDULER_MODE": "gateway"}


def test_defaults(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    cfg = load_gateway_config()
    assert cfg.gateway_host == "127.0.0.1"
    assert cfg.gateway_port == 18789


def test_gateway_host_override(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("GATEWAY_HOST", "0.0.0.0")
    cfg = load_gateway_config()
    assert cfg.gateway_host == "0.0.0.0"


def test_gateway_port_override(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("GATEWAY_PORT", "9000")
    cfg = load_gateway_config()
    assert cfg.gateway_port == 9000


def test_gateway_port_is_int(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    cfg = load_gateway_config()
    assert isinstance(cfg.gateway_port, int)


def test_invalid_gateway_port_exits(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("GATEWAY_PORT", "not_a_number")
    with pytest.raises(SystemExit):
        load_gateway_config()


def test_out_of_range_port_exits(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("GATEWAY_PORT", "99999")
    with pytest.raises(SystemExit):
        load_gateway_config()


def test_scheduler_mode_gateway_accepted(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    cfg = load_gateway_config()
    assert cfg.scheduler_mode == "gateway"


def test_returns_gateway_config_instance(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    cfg = load_gateway_config()
    assert isinstance(cfg, GatewayConfig)


def test_inherits_pipeline_config_fields(monkeypatch):
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    cfg = load_gateway_config()
    # Fields inherited from PipelineConfig
    assert hasattr(cfg, "state_store_path")
    assert hasattr(cfg, "poll_interval_minutes")
    assert hasattr(cfg, "lock_timeout_minutes")
    assert hasattr(cfg, "log_path")
    assert hasattr(cfg, "scheduler_mode")
