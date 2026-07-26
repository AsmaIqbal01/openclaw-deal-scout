"""EmailSchedulerConfig — load and validate environment variables for 007."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EmailSchedulerConfig:
    gmail_credentials_path: str
    email_from_address: str
    email_queue_path: str
    email_audit_log_path: str
    email_template_path: str | None
    email_enabled: bool


def load_email_config() -> EmailSchedulerConfig:
    credentials_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "")
    from_address = os.environ.get("EMAIL_FROM_ADDRESS", "")

    errors: list[str] = []
    if not credentials_path:
        errors.append("GMAIL_CREDENTIALS_PATH is required but not set")
    if not from_address:
        errors.append("EMAIL_FROM_ADDRESS is required but not set")
    if errors:
        for e in errors:
            print(f"[email_scheduler] config error: {e}", file=sys.stderr)
        sys.exit(1)

    state_store_path = os.environ.get("STATE_STORE_PATH", "processed_ids.json")
    default_dir = str(Path(state_store_path).parent)

    queue_path = os.environ.get(
        "EMAIL_QUEUE_PATH",
        str(Path(default_dir) / "email_queue.json"),
    )
    audit_log_path = os.environ.get(
        "EMAIL_AUDIT_LOG_PATH",
        str(Path(default_dir) / "email_audit.log"),
    )
    template_path = os.environ.get("EMAIL_TEMPLATE_PATH") or None

    enabled_str = os.environ.get("EMAIL_ENABLED", "true").lower().strip()
    if enabled_str not in ("true", "false", "1", "0", "yes", "no"):
        print(
            f"[email_scheduler] config error: EMAIL_ENABLED must be true/false/1/0/yes/no, "
            f"got '{enabled_str}'",
            file=sys.stderr,
        )
        sys.exit(1)
    enabled = enabled_str in ("true", "1", "yes")

    return EmailSchedulerConfig(
        gmail_credentials_path=credentials_path,
        email_from_address=from_address,
        email_queue_path=queue_path,
        email_audit_log_path=audit_log_path,
        email_template_path=template_path,
        email_enabled=enabled,
    )
