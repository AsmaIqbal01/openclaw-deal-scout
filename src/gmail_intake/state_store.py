import dataclasses
import json
import logging
import os
import tempfile
from datetime import datetime

import portalocker

from gmail_intake.models import (
    ConcurrentInvocationError,
    ProcessedMessage,
    StateStore,
    StateStoreReadError,
)

logger = logging.getLogger(__name__)

_STORE_WARN_BYTES = 50 * 1024 * 1024  # 50 MB


def read_store(path: str) -> StateStore:
    """
    Deserialise the state store JSON file.

    - File absent → first run; return empty StateStore (not an error).
    - File unreadable or top-level JSON invalid → log ERROR, raise StateStoreReadError.
    - Malformed last_poll_time → log WARN, treat as None, continue (never fatal).
    """
    if not os.path.exists(path):
        return StateStore(last_poll_time=None)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except OSError as exc:
        logger.error("state store unreadable: %s — polling suspended", exc)
        raise StateStoreReadError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        logger.error("state store unreadable: invalid JSON — polling suspended")
        raise StateStoreReadError("invalid JSON") from exc

    if not isinstance(raw, dict):
        logger.error("state store unreadable: invalid JSON — polling suspended")
        raise StateStoreReadError("top-level value is not a JSON object")

    last_poll_time: str | None = raw.get("last_poll_time")
    if last_poll_time is not None:
        if not _is_valid_iso8601(last_poll_time):
            logger.warning(
                "state store: last_poll_time malformed — defaulting to 24-hour window"
            )
            last_poll_time = None

    try:
        messages = [
            ProcessedMessage(
                gmail_message_id=m["gmail_message_id"],
                processed_at=m["processed_at"],
                outcome=m["outcome"],
            )
            for m in raw.get("messages", [])
        ]
    except (KeyError, TypeError) as exc:
        logger.error("state store unreadable: corrupted message entry — polling suspended")
        raise StateStoreReadError("corrupted message entry") from exc

    return StateStore(last_poll_time=last_poll_time, messages=messages)


def _is_valid_iso8601(value: str) -> bool:
    """Return True if value parses as an ISO 8601 UTC datetime string."""
    try:
        # Python 3.11+ accepts the 'Z' suffix directly; replace for older compat
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False


def acquire_lock(path: str) -> portalocker.Lock:
    """
    Acquire an exclusive, non-blocking lock on f"{path}.lock".

    Raises ConcurrentInvocationError immediately if another invocation
    already holds the lock. Caller must release the returned lock in
    a finally block.
    """
    lock_path = f"{path}.lock"
    lock = portalocker.Lock(lock_path, mode="a", flags=portalocker.LOCK_EX | portalocker.LOCK_NB)
    try:
        lock.acquire()
    except portalocker.exceptions.LockException as exc:
        logger.warning("concurrent invocation detected — aborting")
        raise ConcurrentInvocationError("concurrent invocation detected — aborting") from exc
    return lock


def _atomic_write(
    path: str,
    store: StateStore,
    *,
    _new_message_extra: dict | None = None,
) -> None:
    """Merge-write the state store, preserving unknown top-level keys and message extra fields.

    Reads any existing JSON first so that keys like `consecutive_401_cycles`
    added by crm_logger are never silently clobbered.  Extra fields on
    existing message entries (e.g. deal payload fields added by T040) are
    also preserved by merging the ProcessedMessage dict on top of the stored raw dict.

    `_new_message_extra` is applied to the one newly-appended message
    (identified by absence from the existing messages dict).
    """
    # Read existing raw JSON to get current top-level keys and message extra fields
    existing_raw: dict = {}
    existing_by_id: dict[str, dict] = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                existing_raw = raw
                for m in raw.get("messages", []):
                    if isinstance(m, dict) and "gmail_message_id" in m:
                        existing_by_id[m["gmail_message_id"]] = m
        except (OSError, json.JSONDecodeError):
            pass  # File corrupt or missing — start from scratch

    # Build merged messages list, preserving extra fields from existing raw entries
    merged_messages = []
    for m in store.messages:
        msg_dict = dataclasses.asdict(m)
        msg_id = msg_dict.get("gmail_message_id")
        existing_entry = existing_by_id.get(msg_id or "", {})

        if existing_entry:
            # Existing entry: preserve extra fields, let ProcessedMessage dict win on shared keys
            merged_messages.append({**existing_entry, **msg_dict})
        elif _new_message_extra and msg_id and msg_id not in existing_by_id:
            # Newly-appended entry: merge extra payload fields under the ProcessedMessage dict
            merged_messages.append({**_new_message_extra, **msg_dict})
        else:
            merged_messages.append(msg_dict)

    payload = {
        **existing_raw,            # Preserve all existing top-level keys first
        "last_poll_time": store.last_poll_time,
        "messages": merged_messages,
    }

    dir_path = os.path.dirname(os.path.abspath(path)) or "."
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=dir_path, suffix=".tmp", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            tmp_path = fh.name
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.warning("state store write failed: %s", exc)


def append_message(
    path: str,
    store: StateStore,
    entry: ProcessedMessage,
    *,
    extra_fields: dict | None = None,
) -> None:
    """
    Append entry to store.messages in memory, then atomically persist the
    full updated store to disk. Write failures are logged, not raised —
    the message will simply be re-evaluated on the next run.

    extra_fields: optional dict of additional payload fields (e.g. the 9
    DealPayload fields) to persist alongside the ProcessedMessage entry.
    """
    store.messages.append(entry)
    _atomic_write(path, store, _new_message_extra=extra_fields)


def update_poll_time(path: str, store: StateStore, ts: str) -> None:
    """Set store.last_poll_time and atomically persist the store."""
    store.last_poll_time = ts
    _atomic_write(path, store)


def check_store_size(path: str) -> None:
    """Log a WARN once per cycle if the state store exceeds 50 MB."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return  # File doesn't exist yet on first run — not an error
    if size > _STORE_WARN_BYTES:
        logger.warning(
            "state store exceeding %.1f MB — archival recommended", size / (1024 * 1024)
        )
