"""Readers for pipeline.log (JSONL) and processed_ids.json (state store)."""
from __future__ import annotations

import collections
import json
from datetime import datetime, timezone
from typing import Any


def _iter_log(log_path) -> list[dict]:
    """Yield parsed JSONL dicts from log_path; skip missing file and bad lines."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return


def read_pipeline_log(n: int, config) -> list[dict]:
    """Return the last *n* PipelineCycle dicts from config.log_path."""
    return list(collections.deque(_iter_log(config.log_path), maxlen=n))


_STATUS_FILTERS: dict[str, Any] = {
    "crm_pending": lambda e: e.get("crm_status") == "pending",
    "crm_failed": lambda e: e.get("crm_status") == "failed",
    "notify_pending": lambda e: e.get("notify_status") == "pending",
    "notify_failed": lambda e: e.get("notify_status") == "failed",
    "complete": lambda e: e.get("crm_status") == "logged" and e.get("notify_status") == "sent",
}


def read_deals(limit: int, status_filter: str, config) -> list[dict]:
    """Return up to *limit* DealRecord dicts from config.state_store_path.

    Filters by status_filter: "all" | "crm_pending" | "crm_failed" |
    "notify_pending" | "notify_failed" | "complete".
    Returns newest first (reverse insertion order).
    """
    try:
        with open(config.state_store_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []

    messages = data.get("messages", [])
    deals = [m for m in messages if m.get("outcome") == "deal_extracted"]

    if status_filter != "all":
        pred = _STATUS_FILTERS.get(status_filter)
        if pred:
            deals = [d for d in deals if pred(d)]

    # Newest first, then limit
    return deals[::-1][:limit]


def compute_quota_usage(config) -> dict:
    """Estimate Gemini API usage for the current UTC calendar day from pipeline.log."""
    window_date = datetime.now(timezone.utc).date().isoformat()

    cycles_today = [
        entry for entry in _iter_log(config.log_path)
        if entry.get("ts", "").startswith(window_date)
    ]

    estimated_requests_today = sum(c.get("emails_processed", 0) for c in cycles_today)
    daily_limit = 1500
    estimated_remaining = max(0, daily_limit - estimated_requests_today)
    pct_used = min(100.0, estimated_requests_today / daily_limit * 100)
    has_quota_error_today = any(
        "quota_exhausted" in c.get("errors", []) for c in cycles_today
    )

    return {
        "estimated_requests_today": estimated_requests_today,
        "daily_free_tier_limit": daily_limit,
        "estimated_remaining": estimated_remaining,
        "pct_used": round(pct_used, 4),
        "window_date": window_date,
        "cycles_today": len(cycles_today),
        "has_quota_error_today": has_quota_error_today,
    }
