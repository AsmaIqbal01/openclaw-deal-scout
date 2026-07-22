"""Unit tests for pipeline_orchestrator.config — T006."""
import os
import pytest

from pipeline_orchestrator.config import load_config


def _base_env(tmp_path, extra=None):
    env = {"STATE_STORE_PATH": str(tmp_path / "processed_ids.json")}
    if extra:
        env.update(extra)
    return env


class TestLoadConfig:
    def test_valid_minimal_config(self, monkeypatch, tmp_path):
        for key in ("STATE_STORE_PATH", "POLL_INTERVAL_MINUTES", "LOCK_TIMEOUT_MINUTES",
                    "PIPELINE_LOG_PATH", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT",
                    "MAX_PENDING_RETRIES", "SCHEDULER_MODE"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "processed_ids.json"))

        cfg = load_config()

        assert cfg.state_store_path == tmp_path / "processed_ids.json"
        assert cfg.poll_interval_minutes == 15
        assert cfg.lock_timeout_minutes == 30
        assert cfg.log_max_bytes == 10_485_760
        assert cfg.log_backup_count == 3
        assert cfg.max_pending_retries == 10
        assert cfg.scheduler_mode == "loop"

    def test_missing_state_store_path(self, monkeypatch):
        monkeypatch.delenv("STATE_STORE_PATH", raising=False)
        with pytest.raises(SystemExit):
            load_config()

    def test_poll_interval_zero(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("POLL_INTERVAL_MINUTES", "0")
        with pytest.raises(SystemExit):
            load_config()

    def test_poll_interval_not_integer(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("POLL_INTERVAL_MINUTES", "abc")
        with pytest.raises(SystemExit):
            load_config()

    def test_lock_timeout_zero(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("LOCK_TIMEOUT_MINUTES", "0")
        with pytest.raises(SystemExit):
            load_config()

    def test_log_max_bytes_zero(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("LOG_MAX_BYTES", "0")
        with pytest.raises(SystemExit):
            load_config()

    def test_log_backup_count_negative(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("LOG_BACKUP_COUNT", "-1")
        with pytest.raises(SystemExit):
            load_config()

    def test_max_pending_retries_zero(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("MAX_PENDING_RETRIES", "0")
        with pytest.raises(SystemExit):
            load_config()

    def test_invalid_scheduler_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("SCHEDULER_MODE", "cron")
        with pytest.raises(SystemExit):
            load_config()

    def test_defaults_applied(self, monkeypatch, tmp_path):
        for key in ("POLL_INTERVAL_MINUTES", "LOCK_TIMEOUT_MINUTES", "PIPELINE_LOG_PATH",
                    "LOG_MAX_BYTES", "LOG_BACKUP_COUNT", "MAX_PENDING_RETRIES", "SCHEDULER_MODE"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "processed_ids.json"))

        cfg = load_config()

        assert cfg.poll_interval_minutes == 15
        assert cfg.lock_timeout_minutes == 30
        assert cfg.log_path == tmp_path / "pipeline.log"
        assert cfg.log_max_bytes == 10_485_760
        assert cfg.log_backup_count == 3
        assert cfg.max_pending_retries == 10
        assert cfg.scheduler_mode == "loop"

    def test_lock_path_property(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "processed_ids.json"))
        cfg = load_config()
        assert cfg.lock_path == tmp_path / ".pipeline.lock"

    def test_custom_values_accepted(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "store.json"))
        monkeypatch.setenv("POLL_INTERVAL_MINUTES", "5")
        monkeypatch.setenv("LOCK_TIMEOUT_MINUTES", "60")
        monkeypatch.setenv("MAX_PENDING_RETRIES", "3")
        monkeypatch.setenv("SCHEDULER_MODE", "systemd")

        cfg = load_config()

        assert cfg.poll_interval_minutes == 5
        assert cfg.lock_timeout_minutes == 60
        assert cfg.max_pending_retries == 3
        assert cfg.scheduler_mode == "systemd"
