import json
import logging
import os
import tempfile
from typing import Any

import portalocker

from crm_logger.models import CrmStateStore, CrmStateStoreReadError

logger = logging.getLogger(__name__)


def _raw_load(path: str) -> dict:
    """Read the raw JSON dict from path; return default skeleton if file absent."""
    if not os.path.exists(path):
        return {"last_poll_time": None, "messages": [], "consecutive_401_cycles": 0}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except OSError as exc:
        raise CrmStateStoreReadError(f"unreadable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CrmStateStoreReadError("invalid JSON") from exc
    if not isinstance(raw, dict):
        raise CrmStateStoreReadError("top-level value is not a JSON object")
    return raw


def _merge_write(path: str, updates: dict[str, Any]) -> None:
    """Atomic merge-write: read existing JSON, apply updates, write back atomically.

    Preserves all top-level keys not in `updates` so gmail_intake writes never
    clobber consecutive_401_cycles and vice-versa.
    """
    raw = _raw_load(path)
    raw.update(updates)
    dir_path = os.path.dirname(os.path.abspath(path)) or "."
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=dir_path, suffix=".tmp", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(raw, fh, indent=2, ensure_ascii=False)
            tmp_path = fh.name
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.warning("state store write failed: %s", exc)


def acquire_lock(path: str) -> portalocker.Lock:
    """Acquire exclusive non-blocking lock on path.lock."""
    lock_path = f"{path}.lock"
    lock = portalocker.Lock(lock_path, mode="a", flags=portalocker.LOCK_EX | portalocker.LOCK_NB)
    lock.acquire()
    return lock


def read_crm_store(path: str) -> CrmStateStore:
    """Deserialise the state store, returning all fields including CRM extensions."""
    raw = _raw_load(path)
    return CrmStateStore(
        last_poll_time=raw.get("last_poll_time"),
        consecutive_401_cycles=int(raw.get("consecutive_401_cycles", 0)),
        messages=raw.get("messages", []),
    )


def get_pending_deals(store: CrmStateStore) -> list[dict]:
    """Return message dicts with status 'crm-pending'."""
    return [m for m in store.messages if m.get("status") == "crm-pending"]


def get_new_deals(store: CrmStateStore) -> list[dict]:
    """Return message dicts with status 'deal_extracted'."""
    return [m for m in store.messages if m.get("status") == "deal_extracted"]


def write_crm_outcome(
    path: str,
    gmail_message_id: str,
    outcome: str,
    **extra_fields: Any,
) -> None:
    """Atomically update a single message entry's status and any extra fields."""
    raw = _raw_load(path)
    messages = raw.get("messages", [])
    for msg in messages:
        if msg.get("gmail_message_id") == gmail_message_id:
            msg["status"] = outcome
            msg.update(extra_fields)
            break
    _merge_write(path, {"messages": messages})


def read_401_counter(path: str) -> int:
    """Return the consecutive_401_cycles counter value (default 0)."""
    raw = _raw_load(path)
    return int(raw.get("consecutive_401_cycles", 0))


def write_401_counter(path: str, value: int) -> None:
    """Atomically set the consecutive_401_cycles counter to value."""
    _merge_write(path, {"consecutive_401_cycles": value})
