"""pipeline_orchestrator.runner — wire steps 1 → 2 → 3 into a single pipeline cycle."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import google.auth.exceptions

from gmail_intake.models import RateLimitExhaustedError
from gmail_intake.server import check_new_deals_handler
from crm_logger.server import sync_deals_to_crm
from discord_notifier.server import sync_notifications

from pipeline_orchestrator.config import PipelineConfig
from pipeline_orchestrator.cycle_logger import CycleLogger
from pipeline_orchestrator.lock import CycleLock, CycleLockActiveError  # noqa: F401 (re-exported)

logger = logging.getLogger(__name__)

_CRM_LOGGED_STATUSES = {"crm-logged", "crm-logged-notify-pending", "discord-notified"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_store_raw(state_path: Path) -> dict:
    try:
        with open(state_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_store_raw(state_path: Path, data: dict) -> None:
    dir_path = state_path.parent
    with tempfile.NamedTemporaryFile(
        mode="w", dir=str(dir_path), suffix=".tmp", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp_path = fh.name
    os.replace(tmp_path, str(state_path))


def _update_crm_retry(state_path: Path, config: PipelineConfig, errors: list[str]) -> None:
    """After step 2: write crm_status, increment crm_retry_count, promote when limit reached."""
    if not state_path.exists():
        return
    try:
        data = _read_store_raw(state_path)
        if not data:
            return
        messages = data.get("messages", [])
        promoted = False
        for msg in messages:
            status = msg.get("status", "")
            if status in _CRM_LOGGED_STATUSES:
                msg["crm_status"] = "logged"
                msg["crm_retry_count"] = 0
            elif status == "crm-pending":
                count = msg.get("crm_retry_count", 0) + 1
                msg["crm_retry_count"] = count
                if count >= config.max_pending_retries:
                    msg["crm_status"] = "failed"
                    promoted = True
                else:
                    msg["crm_status"] = "pending"
        if promoted and "pending_promoted_to_failed" not in errors:
            errors.append("pending_promoted_to_failed")
        data["messages"] = messages
        _write_store_raw(state_path, data)
    except Exception:
        logger.exception("crm retry update: unexpected error reading/writing state store")


def _update_notify_retry(state_path: Path, config: PipelineConfig, errors: list[str]) -> None:
    """After step 3: write notify_status, increment notify_retry_count, promote when limit reached."""
    if not state_path.exists():
        return
    try:
        data = _read_store_raw(state_path)
        if not data:
            return
        messages = data.get("messages", [])
        promoted = False
        for msg in messages:
            status = msg.get("status", "")
            if status == "discord-notified":
                msg["notify_status"] = "sent"
                msg["notify_retry_count"] = 0
            elif status == "crm-logged-notify-pending":
                count = msg.get("notify_retry_count", 0) + 1
                msg["notify_retry_count"] = count
                if count >= config.max_pending_retries:
                    msg["notify_status"] = "failed"
                    promoted = True
                else:
                    msg["notify_status"] = "pending"
        if promoted and "pending_promoted_to_failed" not in errors:
            errors.append("pending_promoted_to_failed")
        data["messages"] = messages
        _write_store_raw(state_path, data)
    except Exception:
        logger.exception("notify retry update: unexpected error reading/writing state store")


def _classify_step1_error(error_details: str | None) -> str:
    details = (error_details or "").lower()
    if any(kw in details for kw in ("auth", "credential", "token", "refresh", "oauth")):
        return "gmail_oauth_failed"
    if any(kw in details for kw in ("state store", "unreadable")):
        return "state_store_unreadable"
    return "unhandled_exception"


def run_cycle(config: PipelineConfig, cycle_logger: CycleLogger) -> None:
    """Run one pipeline cycle: step 1 → step 2 → step 3.

    CycleLockActiveError propagates to the caller (run_loop skips, systemd mode exits non-zero).
    All other exceptions are caught, logged, and reflected in the cycle summary errors list.
    The cycle summary is always emitted in the finally block.
    """
    errors: list[str] = []
    emails_processed = 0
    crm_logged = 0
    notified = 0
    pending = 0

    with CycleLock(config.lock_path, config.lock_timeout_minutes):
        try:
            # ── Step 1: Gmail intake ──────────────────────────────────────────
            step1_abort = False
            result1: dict = {
                "status": "ok",
                "deals_extracted": [],
                "processed_count": 0,
                "skipped_count": 0,
                "error_details": None,
            }
            try:
                result1 = asyncio.run(check_new_deals_handler())
            except RateLimitExhaustedError:
                logger.warning("step 1: RateLimitExhaustedError — quota exhausted")
                errors.append("quota_exhausted")
                # steps 2+3 still run to drain already-classified entries (FR-022)
            except google.auth.exceptions.RefreshError:
                logger.error("step 1: Google auth RefreshError")
                errors.append("gmail_oauth_failed")
                step1_abort = True
            except Exception:
                logger.exception("step 1: unhandled exception")
                errors.append("unhandled_exception")
                step1_abort = True

            if not step1_abort and result1.get("status") == "error":
                token = _classify_step1_error(result1.get("error_details"))
                if token not in errors:
                    errors.append(token)
                step1_abort = True

            emails_processed = result1.get("processed_count", 0)

            if step1_abort:
                return  # finally still fires (emit summary with partial data)

            # ── Step 2: CRM sync ──────────────────────────────────────────────
            result2: dict = {
                "status": "ok",
                "crm_logged": 0,
                "crm_pending": 0,
                "skipped": 0,
                "suspended": False,
                "error_details": None,
            }
            try:
                result2 = sync_deals_to_crm()
            except Exception:
                logger.exception("step 2: unhandled exception")
                if "unhandled_exception" not in errors:
                    errors.append("unhandled_exception")

            if result2.get("suspended"):
                if "crm_suspended" not in errors:
                    errors.append("crm_suspended")
            elif result2.get("status") == "error":
                if "unhandled_exception" not in errors:
                    errors.append("unhandled_exception")

            crm_logged = result2.get("crm_logged", 0)
            _update_crm_retry(config.state_store_path, config, errors)

            # ── Step 3: Discord notifications (always runs after step 2) ──────
            result3: dict = {
                "status": "ok",
                "discord_notified": 0,
                "notify_pending": 0,
                "skipped": 0,
                "error_details": None,
            }
            try:
                result3 = sync_notifications()
            except Exception:
                logger.exception("step 3: unhandled exception")
                if "unhandled_exception" not in errors:
                    errors.append("unhandled_exception")

            if result3.get("status") == "error":
                if "unhandled_exception" not in errors:
                    errors.append("unhandled_exception")

            notified = result3.get("discord_notified", 0)
            _update_notify_retry(config.state_store_path, config, errors)

            pending = result2.get("crm_pending", 0) + result3.get("notify_pending", 0)

        finally:
            cycle_logger.emit_cycle_summary(
                ts=_utcnow_iso(),
                emails_processed=emails_processed,
                crm_logged=crm_logged,
                notified=notified,
                pending=pending,
                errors=errors,
            )
