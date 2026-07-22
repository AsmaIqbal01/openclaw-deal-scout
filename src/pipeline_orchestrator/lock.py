"""CycleLock — file-based lock preventing concurrent pipeline cycles."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%SZ"


class CycleLockActiveError(Exception):
    """Raised when a non-stale .pipeline.lock already exists."""


class CycleLock:
    def __init__(self, lock_path: Path, timeout_minutes: int) -> None:
        self._path = lock_path
        self._timeout_minutes = timeout_minutes

    def __enter__(self) -> "CycleLock":
        if self._path.exists():
            raw = self._path.read_text(encoding="utf-8").strip()
            age_minutes: float | None = None
            try:
                created = datetime.strptime(raw, _TIMESTAMP_FMT).replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                age_minutes = (now - created).total_seconds() / 60
            except ValueError:
                logger.warning(
                    "lock: malformed timestamp %r — treating as stale, clearing", raw
                )

            if age_minutes is not None and age_minutes < self._timeout_minutes:
                raise CycleLockActiveError(
                    f"active lock (created {raw}, age {age_minutes:.1f} min)"
                )

            # Stale or malformed — clear it
            if age_minutes is not None:
                logger.warning(
                    "lock: stale lock detected (created %s, age %.1f min ≥ %d min) — clearing",
                    raw,
                    age_minutes,
                    self._timeout_minutes,
                )
            try:
                self._path.unlink()
            except OSError as exc:
                logger.warning("lock: could not remove old lock file: %s", exc)

        ts = datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)
        try:
            self._path.write_text(ts, encoding="utf-8")
        except OSError as exc:
            logger.error("lock: could not create lock file at %s: %s", self._path, exc)
            raise
        return self

    def __exit__(self, *_: object) -> None:
        try:
            self._path.unlink()
        except OSError as exc:
            logger.warning("lock: could not delete lock file on exit: %s", exc)
