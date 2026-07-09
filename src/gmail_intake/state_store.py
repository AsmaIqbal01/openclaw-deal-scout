import json
import logging
import os
from datetime import datetime

from gmail_intake.models import ProcessedMessage, StateStore, StateStoreReadError

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
