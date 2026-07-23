"""PipelineConfig — read and validate all env vars at startup."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PipelineConfig:
    state_store_path: Path
    poll_interval_minutes: int
    lock_timeout_minutes: int
    log_path: Path
    log_max_bytes: int
    log_backup_count: int
    max_pending_retries: int
    scheduler_mode: str

    @property
    def lock_path(self) -> Path:
        return self.state_store_path.parent / ".pipeline.lock"


def _require_str(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"[pipeline_orchestrator] ERROR: {name} is required but not set or empty")
    return value


def _int_ge(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        sys.exit(
            f"[pipeline_orchestrator] ERROR: {name}={raw!r} is not a valid integer"
        )
    if value < minimum:
        sys.exit(
            f"[pipeline_orchestrator] ERROR: {name}={value} is below minimum {minimum}"
        )
    return value


def _int_ge0(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        sys.exit(
            f"[pipeline_orchestrator] ERROR: {name}={raw!r} is not a valid integer"
        )
    if value < 0:
        sys.exit(f"[pipeline_orchestrator] ERROR: {name}={value} must be ≥ 0")
    return value


def load_config() -> PipelineConfig:
    """Read and validate all env vars. Calls sys.exit(1) on any error."""
    state_store_raw = _require_str("STATE_STORE_PATH")
    state_store_path = Path(state_store_raw)

    poll_interval = _int_ge("POLL_INTERVAL_MINUTES", 15, 1)
    lock_timeout = _int_ge("LOCK_TIMEOUT_MINUTES", 30, 1)

    default_log = str(state_store_path.parent / "pipeline.log")
    log_path_raw = os.environ.get("PIPELINE_LOG_PATH", default_log).strip()
    if not log_path_raw:
        sys.exit("[pipeline_orchestrator] ERROR: PIPELINE_LOG_PATH is set but empty")
    log_path = Path(log_path_raw)

    log_max_bytes = _int_ge("LOG_MAX_BYTES", 10_485_760, 1)
    log_backup_count = _int_ge0("LOG_BACKUP_COUNT", 3)
    max_pending_retries = _int_ge("MAX_PENDING_RETRIES", 10, 1)

    scheduler_mode_raw = os.environ.get("SCHEDULER_MODE", "loop").strip().lower()
    if scheduler_mode_raw not in ("loop", "systemd", "gateway"):
        sys.exit(
            f"[pipeline_orchestrator] ERROR: SCHEDULER_MODE={scheduler_mode_raw!r} "
            "must be 'loop', 'systemd', or 'gateway'"
        )

    return PipelineConfig(
        state_store_path=state_store_path,
        poll_interval_minutes=poll_interval,
        lock_timeout_minutes=lock_timeout,
        log_path=log_path,
        log_max_bytes=log_max_bytes,
        log_backup_count=log_backup_count,
        max_pending_retries=max_pending_retries,
        scheduler_mode=scheduler_mode_raw,
    )
