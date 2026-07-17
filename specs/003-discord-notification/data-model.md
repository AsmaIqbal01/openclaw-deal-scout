# Data Model: Discord Deal Notification

**Feature**: `003-discord-notification`
**Date**: 2026-07-17

---

## Shared State Store Extension

No new file is introduced. The existing `processed_ids.json` message entries
are extended with notification-lifecycle fields. All reads and writes use the
same atomic merge-write pattern as Step 2 (`crm_logger/state_store.py`).

### Message Entry Schema (full lifecycle, all three steps)

```json
{
  "gmail_message_id": "string — non-empty; primary key",
  "processed_at":     "string — ISO 8601 UTC; set by gmail_intake on first write",
  "outcome":          "string — gmail_intake outcome literal (see below)",
  "status":           "string — pipeline lifecycle status (see State Transitions)",

  // Fields written by gmail_intake (FR-015 of Step 2):
  "sender_email":     "string — non-empty, contains '@'",
  "sender_name":      "string | null — null if absent from From header",
  "subject":          "string — non-empty, max 255 chars after Step 2 truncation",
  "received_at":      "string — ISO 8601 UTC from Gmail internalDate",
  "deal_summary":     "string — 1–2 sentences, max 500 chars",
  "deal_category":    "string — one of: lead | partnership_inquiry | vendor_offer | rfq | other",
  "confidence_score": "float — 0.0–1.0 inclusive",
  "raw_email_excerpt":"string | null — max 500 chars; null if body absent",

  // Fields written by crm_logger (Step 2):
  "contact_id":       "string | null — HubSpot contact ID on crm-logged",
  "deal_id":          "string | null — HubSpot deal ID on crm-logged",
  "error_reason":     "string | null — set on crm-pending; cleared on crm-logged",

  // Fields written by discord_notifier (Step 3 — NEW):
  "notified_at":      "string | null — ISO 8601 UTC; written ONLY on discord-notified",
  "notify_error_reason": "string | null — max 255 chars; written on crm-logged-notify-pending"
}
```

> Note: `error_reason` (CRM) and `notify_error_reason` (Discord) are separate
> fields to avoid collision. Both are preserved by merge-write.

### Status Lifecycle

```
deal_extracted
  │
  ▼ (crm_logger)
crm-pending ──retry──► crm-logged
                              │
                              ▼ (discord_notifier)
             crm-logged-notify-pending ──retry──► discord-notified  ← TERMINAL
```

All other gmail_intake terminal statuses (`not_a_deal`, `body_absent`,
`invalid_metadata`, `rate_limited`, `classification_error`, `schema_error`)
are never touched by discord_notifier.

---

## Python Data Types

### `NotifyOutcome` (Literal)

```python
NotifyOutcome = Literal["discord-notified", "crm-logged-notify-pending", "skipped"]
```

| Value | Meaning |
|-------|---------|
| `"discord-notified"` | Delivery confirmed (HTTP 2xx) and state written |
| `"crm-logged-notify-pending"` | Delivery failed; entry left retryable |
| `"skipped"` | Already `discord-notified`; idempotency no-op |

### `NotificationCycleResult` (dataclass)

```python
@dataclass
class NotificationCycleResult:
    status: str                     # "ok" | "error"
    discord_notified: int = 0
    notify_pending: int = 0
    skipped: int = 0
    error_details: str | None = None
```

### Exception Hierarchy

```python
class DiscordWebhookError(Exception):
    def __init__(self, status_code: int, body: str) -> None: ...
    # status_code: HTTP status int
    # body: first 200 chars of response body

class DiscordRateLimitError(DiscordWebhookError):
    # Raised on HTTP 429; retry_after from response header stored in message

class DiscordTimeoutError(Exception):
    # Raised when requests raises Timeout (connect or read > 10 s)
```

### `NotifierContract` (Protocol)

```python
from typing import Protocol, Literal

class NotifierContract(Protocol):
    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]:
        """
        Attempt to deliver a notification for the given deal dict.
        MUST NOT raise exceptions — return "crm-logged-notify-pending" on any failure.
        """
        ...
```

### Discord Embed Payload (output of `formatter.format_embed`)

```python
{
    "embeds": [
        {
            "title": str,   # deal subject, max 256 chars (truncated with '...' if longer)
            "description": str,  # deal_summary; "(no summary)" if empty
            "fields": [
                {
                    "name": "From",
                    "value": "{sender_name} <{sender_email}>" if sender_name else "{sender_email}",
                    "inline": True
                },
                {
                    "name": "Category",
                    "value": str,   # deal_category value verbatim
                    "inline": True
                },
                {
                    "name": "Confidence",
                    "value": str,   # f"{round(confidence_score * 100)}%"
                    "inline": True
                }
            ]
        }
    ]
}
```

Confidence score is rounded to the nearest integer percentage (`round()`, no
decimal places). `raw_email_excerpt`, `received_at`, and `gmail_message_id`
are omitted from the embed body; they remain in the state store only.

---

## Validation Rules

| Field | Rule | Enforced by |
|-------|------|-------------|
| `notified_at` | Written ONLY when HTTP 2xx received AND state-store write succeeds | `notifier.py` |
| `notify_error_reason` | Max 255 chars; min content = HTTP status code or exception class name | `notifier.py` |
| `status` (notify path) | Only transitions: `crm-logged` → `discord-notified` or `crm-logged-notify-pending`; and `crm-logged-notify-pending` → same options | `state_store.py` write guard |
| `NOTIFIER` env var | Required; must be a known adapter name; fail-fast on missing/unknown | `orchestrator.py` startup |
| `DISCORD_WEBHOOK_URL` | Required when `NOTIFIER=discord`; non-empty string; validated at adapter construction | `adapter.py` __init__ |

---

## State Store Read Functions

| Function | Returns | Filter |
|----------|---------|--------|
| `read_notify_store(path)` | raw JSON dict | — |
| `get_ready_to_notify(store)` | `list[dict]` | `status == "crm-logged"` |
| `get_pending_notifications(store)` | `list[dict]` | `status == "crm-logged-notify-pending"` |

Processing order per cycle: `get_pending_notifications()` first, then
`get_ready_to_notify()` (drain-first, consistent with Step 2).
