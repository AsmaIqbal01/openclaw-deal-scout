"""Unit tests for email_scheduler.config.load_email_config() — T010."""
from __future__ import annotations

import pytest

from email_scheduler.config import EmailSchedulerConfig, load_email_config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "GMAIL_CREDENTIALS_PATH",
        "EMAIL_FROM_ADDRESS",
        "EMAIL_QUEUE_PATH",
        "EMAIL_AUDIT_LOG_PATH",
        "EMAIL_TEMPLATE_PATH",
        "EMAIL_ENABLED",
        "STATE_STORE_PATH",
    ):
        monkeypatch.delenv(var, raising=False)


def _set_required(monkeypatch, creds="/tmp/creds.json", addr="test@example.com"):
    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", creds)
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", addr)


class TestRequiredVars:
    def test_valid_minimal_config_returns_dataclass(self, monkeypatch):
        _set_required(monkeypatch)
        cfg = load_email_config()
        assert isinstance(cfg, EmailSchedulerConfig)
        assert cfg.gmail_credentials_path == "/tmp/creds.json"
        assert cfg.email_from_address == "test@example.com"

    def test_missing_credentials_path_exits(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "test@example.com")
        with pytest.raises(SystemExit):
            load_email_config()

    def test_missing_from_address_exits(self, monkeypatch):
        monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", "/tmp/creds.json")
        with pytest.raises(SystemExit):
            load_email_config()

    def test_both_required_missing_exits(self, monkeypatch):
        with pytest.raises(SystemExit):
            load_email_config()

    def test_exit_code_is_one_on_missing_vars(self, monkeypatch):
        with pytest.raises(SystemExit) as exc_info:
            load_email_config()
        assert exc_info.value.code == 1


class TestDefaults:
    def test_queue_path_defaults_to_state_store_dir(self, monkeypatch, tmp_path):
        _set_required(monkeypatch)
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "processed_ids.json"))
        cfg = load_email_config()
        assert cfg.email_queue_path == str(tmp_path / "email_queue.json")

    def test_audit_log_defaults_to_state_store_dir(self, monkeypatch, tmp_path):
        _set_required(monkeypatch)
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "processed_ids.json"))
        cfg = load_email_config()
        assert cfg.email_audit_log_path == str(tmp_path / "email_audit.log")

    def test_template_path_defaults_to_none(self, monkeypatch):
        _set_required(monkeypatch)
        cfg = load_email_config()
        assert cfg.email_template_path is None

    def test_email_enabled_defaults_to_true(self, monkeypatch):
        _set_required(monkeypatch)
        cfg = load_email_config()
        assert cfg.email_enabled is True


class TestOptionalOverrides:
    def test_queue_path_override_respected(self, monkeypatch, tmp_path):
        _set_required(monkeypatch)
        custom = str(tmp_path / "myqueue.json")
        monkeypatch.setenv("EMAIL_QUEUE_PATH", custom)
        cfg = load_email_config()
        assert cfg.email_queue_path == custom

    def test_template_path_set_when_provided(self, monkeypatch):
        _set_required(monkeypatch)
        monkeypatch.setenv("EMAIL_TEMPLATE_PATH", "/opt/template.txt")
        cfg = load_email_config()
        assert cfg.email_template_path == "/opt/template.txt"

    def test_email_enabled_false(self, monkeypatch):
        _set_required(monkeypatch)
        monkeypatch.setenv("EMAIL_ENABLED", "false")
        cfg = load_email_config()
        assert cfg.email_enabled is False

    def test_email_enabled_zero(self, monkeypatch):
        _set_required(monkeypatch)
        monkeypatch.setenv("EMAIL_ENABLED", "0")
        cfg = load_email_config()
        assert cfg.email_enabled is False

    def test_email_enabled_yes(self, monkeypatch):
        _set_required(monkeypatch)
        monkeypatch.setenv("EMAIL_ENABLED", "yes")
        cfg = load_email_config()
        assert cfg.email_enabled is True

    def test_invalid_email_enabled_string_exits(self, monkeypatch):
        _set_required(monkeypatch)
        monkeypatch.setenv("EMAIL_ENABLED", "maybe")
        with pytest.raises(SystemExit):
            load_email_config()
