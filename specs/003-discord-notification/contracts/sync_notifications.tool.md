# Contract: `sync_notifications` MCP Tool

**Feature**: `003-discord-notification`
**Server**: `discord-notifier` (FastMCP)
**Date**: 2026-07-17

---

## Overview

`sync_notifications` is the single MCP tool exposed by the `discord_notifier`
FastMCP server. It reads the shared state store, identifies deals ready for
Discord notification, delivers alerts, and updates the state store — all in one
idempotent call. No parameters are accepted; all configuration is via environment
variables.

---

## Signature

```python
@mcp.tool()
def sync_notifications() -> dict:
    """
    Send Discord alerts for all crm-logged deals not yet notified.
    Drain crm-logged-notify-pending entries first, then process new crm-logged entries.
    Returns a NotificationCycleResult as a plain dict.
    No parameters — all config via environment variables.
    """
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NOTIFIER` | Yes | — | Adapter name: `"discord"` or `"noop"`. Missing or unknown value → immediate error, no state written |
| `DISCORD_WEBHOOK_URL` | When `NOTIFIER=discord` | — | Full Discord webhook URL. Stored in `.env` only |
| `STATE_STORE_PATH` | No | `"processed_ids.json"` | Absolute or relative path to state store file |

---

## Response Schema

```json
{
  "status":           "ok" | "error",
  "discord_notified": 0,
  "notify_pending":   0,
  "skipped":          0,
  "error_details":    null
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `"ok"` \| `"error"` | `"ok"` even when some deals are pending (partial success); `"error"` only for cycle-level failures (unreadable store, missing config, state lock) |
| `discord_notified` | int ≥ 0 | Deals successfully delivered this cycle |
| `notify_pending` | int ≥ 0 | Deals that failed delivery and were marked `crm-logged-notify-pending` |
| `skipped` | int ≥ 0 | Deals already `discord-notified` (idempotency no-ops) |
| `error_details` | string \| null | Populated only when `status = "error"`; contains a generic description (not raw exception detail) |

---

## Success Path

1. Acquire state store lock (portalocker)
2. Read `processed_ids.json`
3. Validate `NOTIFIER` env var → instantiate adapter
4. Collect `crm-logged-notify-pending` entries (drain-first)
5. Collect `crm-logged` entries (new deals)
6. For each deal (pending first, then new):
   a. If status is already `discord-notified` → increment `skipped`, continue
   b. Call `adapter.notify(deal)` → returns outcome string
   c. Call `write_notify_outcome(state_path, gmail_message_id, outcome, ...)`
   d. Increment appropriate counter
7. Release lock
8. Return `NotificationCycleResult` as dict

---

## Error Paths

| Trigger | `status` | `discord_notified` | `notify_pending` | `error_details` |
|---------|----------|-------------------|-----------------|-----------------|
| `NOTIFIER` missing or unknown | `"error"` | 0 | 0 | `"NOTIFIER env var missing or unrecognised"` |
| `DISCORD_WEBHOOK_URL` missing | `"error"` | 0 | 0 | `"DISCORD_WEBHOOK_URL not set"` |
| State store lock held by another process | `"error"` | 0 | 0 | `"concurrent invocation"` |
| State store unreadable | `"error"` | 0 | 0 | `"State store unreadable"` |
| State store readable but invalid JSON | `"error"` | 0 | 0 | `"State store parse failed"` |
| Per-deal Discord failure | `"ok"` | ≥ 0 | ≥ 1 | null |
| Zero deals to process | `"ok"` | 0 | 0 | null |

---

## Idempotency

Calling `sync_notifications` multiple times is safe:
- Deals already `discord-notified` → counted in `skipped`, no API call made
- Deals still `crm-logged` or `crm-logged-notify-pending` → retried
- Cycle-level failures (lock contention, bad config) → `"error"` returned, no state written

---

## Test Scenarios (Unit)

```python
# T1: Empty store → ok / 0/0/0
# T2: One crm-logged deal, discord succeeds → ok / 1/0/0
# T3: One crm-logged deal, discord fails → ok / 0/1/0
# T4: One discord-notified deal → ok / 0/0/1  (skipped)
# T5: One pending + one crm-logged, both succeed → ok / 2/0/0
# T6: Missing NOTIFIER → error / 0/0/0
# T7: Concurrent lock → error / 0/0/0
# T8: Invalid JSON store → error / 0/0/0
```
