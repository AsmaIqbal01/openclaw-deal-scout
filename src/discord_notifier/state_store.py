import json
import logging
import os
import tempfile
from typing import Any

import portalocker

from discord_notifier.models import NotifyConcurrentError, NotifyStateStoreReadError

logger = logging.getLogger(__name__)


def _raw_load(path: str) -> dict:
    """Read the raw JSON dict from path; return default skeleton if file absent."""
    if not os.path.exists(path):
        return {"last_poll_time": None, "messages": []}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except OSError as exc:
        raise NotifyStateStoreReadError(f"unreadable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise NotifyStateStoreReadError("invalid JSON") from exc
    if not isinstance(raw, dict):
        raise NotifyStateStoreReadError("top-level value is not a JSON object")
    return raw


def _merge_write(path: str, updates: dict[str, Any]) -> None:
    """Atomic merge-write: read existing JSON, apply updates, write back atomically.

    Preserves all top-level keys not in `updates` (e.g. consecutive_401_cycles
    written by crm_logger). Raises OSError on write failure — callers that need
    to handle FR-016 (delivery-success / state-write-failure split) must catch it.
    """
    raw = _raw_load(path)
    raw.update(updates)
    dir_path = os.path.dirname(os.path.abspath(path)) or "."
    with tempfile.NamedTemporaryFile(
        mode="w", dir=dir_path, suffix=".tmp", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(raw, fh, indent=2, ensure_ascii=False)
        tmp_path = fh.name
    os.replace(tmp_path, path)


def acquire_lock(path: str) -> portalocker.Lock:
    """Acquire an exclusive non-blocking lock on {path}.lock.

    Raises NotifyConcurrentError immediately if another process holds the lock.
    Caller MUST release the returned lock in a finally block.
    """
    lock_path = f"{path}.lock"
    lock = portalocker.Lock(lock_path, mode="a", flags=portalocker.LOCK_EX | portalocker.LOCK_NB)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException as exc:
        logger.warning("concurrent notification invocation detected")
        raise NotifyConcurrentError("concurrent invocation") from exc
    return lock


def read_notify_store(path: str) -> dict:
    """Return the raw state store JSON dict, preserving all fields from all pipeline steps."""
    return _raw_load(path)


def get_ready_to_notify(store: dict) -> list[dict]:
    """Return message dicts with status 'crm-logged' (ready for first notification attempt)."""
    return [m for m in store.get("messages", []) if m.get("status") == "crm-logged"]


def get_pending_notifications(store: dict) -> list[dict]:
    """Return message dicts with status 'crm-logged-notify-pending' (failed, awaiting retry)."""
    return [
        m for m in store.get("messages", [])
        if m.get("status") == "crm-logged-notify-pending"
    ]


def write_notify_outcome(
    path: str,
    gmail_message_id: str,
    outcome: str,
    **extra_fields: Any,
) -> None:
    """Atomically update a single message entry's status and any extra fields.

    Raises:
        KeyError: if gmail_message_id is not found in the state store.
        OSError: if the atomic write fails (callers handle FR-016 path).
    """
    raw = _raw_load(path)
    messages = raw.get("messages", [])
    found = False
    for msg in messages:
        if msg.get("gmail_message_id") == gmail_message_id:
            msg["status"] = outcome
            msg.update(extra_fields)
            found = True
            break
    if not found:
        raise KeyError(f"gmail_message_id not found in state store: {gmail_message_id}")
    _merge_write(path, {"messages": messages})
