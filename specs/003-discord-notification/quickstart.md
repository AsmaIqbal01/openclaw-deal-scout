# Quickstart: Discord Deal Notification

**Feature**: `003-discord-notification`
**Date**: 2026-07-17

---

## Prerequisites

- Steps 1 and 2 are operational: `processed_ids.json` exists with at least one
  entry whose `status = "crm-logged"`.
- Python 3.12 available at `/usr/bin/python3.12` or `~/.local/bin/python3.12`.
- `requests`, `portalocker`, and `fastmcp` installed (already in `pyproject.toml`).

---

## Environment Setup

Add to `.env`:

```bash
NOTIFIER=discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
STATE_STORE_PATH=./data/processed_ids.json  # same as Steps 1 and 2
```

To get a webhook URL: Discord channel → Edit Channel → Integrations → Webhooks
→ New Webhook → Copy Webhook URL.

`.env` is listed in `.gitignore` and MUST NOT be committed.

---

## Running the MCP Server

```bash
# Load .env and start the discord-notifier FastMCP server
source .env && python3.12 -m discord_notifier.server
```

---

## Calling `sync_notifications`

Via OpenClaw MCP client (once the server is registered):

```
sync_notifications()
```

Expected response for a successful cycle:

```json
{
  "status": "ok",
  "discord_notified": 1,
  "notify_pending": 0,
  "skipped": 0,
  "error_details": null
}
```

---

## Integration Test Scenarios

### Scenario 1: Happy Path — One Deal Notified

**Setup**:
```json
// processed_ids.json entry
{
  "gmail_message_id": "abc123",
  "status": "crm-logged",
  "sender_email": "jane@example.com",
  "sender_name": "Jane Smith",
  "subject": "Partnership inquiry",
  "received_at": "2026-07-17T09:00:00Z",
  "deal_summary": "Jane is interested in a joint venture for the UK market.",
  "deal_category": "partnership_inquiry",
  "confidence_score": 0.87,
  "raw_email_excerpt": null
}
```

**Run**: `sync_notifications()`

**Expected**:
- Discord `#deal_alerts` receives one embed with title "Partnership inquiry",
  From "Jane Smith <jane@example.com>", Category "partnership_inquiry",
  Confidence "87%"
- `processed_ids.json` entry updated: `status = "discord-notified"`,
  `notified_at = "<ISO timestamp>"`
- Response: `{ "status": "ok", "discord_notified": 1, "notify_pending": 0, "skipped": 0 }`

---

### Scenario 2: Idempotent Re-run

**Setup**: Same entry as Scenario 1, but `status` is already `"discord-notified"`.

**Run**: `sync_notifications()`

**Expected**:
- No Discord API call is made
- `processed_ids.json` unchanged
- Response: `{ "status": "ok", "discord_notified": 0, "notify_pending": 0, "skipped": 1 }`

---

### Scenario 3: Discord Failure → Pending State

**Setup**: `DISCORD_WEBHOOK_URL` set to a revoked webhook URL.
Entry `status = "crm-logged"`.

**Run**: `sync_notifications()`

**Expected**:
- Discord API returns 4xx or connection error
- `processed_ids.json` entry updated: `status = "crm-logged-notify-pending"`,
  `notify_error_reason = "<error description>"`, `notified_at` absent
- Response: `{ "status": "ok", "discord_notified": 0, "notify_pending": 1, "skipped": 0 }`

---

### Scenario 4: Drain-First — Pending Before New

**Setup**:
- Entry A: `status = "crm-logged-notify-pending"` (previous failure)
- Entry B: `status = "crm-logged"` (new deal)
- Webhook URL valid

**Run**: `sync_notifications()`

**Expected**:
- Entry A is processed first (drain-first ordering)
- Entry B is processed second
- Both transition to `discord-notified`
- Response: `{ "status": "ok", "discord_notified": 2, "notify_pending": 0, "skipped": 0 }`

---

### Scenario 5: Null sender_name Rendering

**Setup**: Entry with `sender_name = null`, `sender_email = "vendor@corp.com"`.

**Run**: `sync_notifications()`

**Expected**: Discord embed "From" field value is `"vendor@corp.com"` (no angle
brackets, no null string).

---

## Dry-Run (No Discord Call)

Set `NOTIFIER=noop` to exercise the full notification cycle without sending a
Discord message. Useful for testing state transitions without a real webhook:

```bash
NOTIFIER=noop STATE_STORE_PATH=./data/processed_ids.json python3.12 -m discord_notifier.server
```

All deals will be marked `discord-notified` as if delivery succeeded.

---

## Running Unit Tests

```bash
~/.local/bin/pytest tests/unit/test_discord_adapter.py \
                    tests/unit/test_notify_formatter.py \
                    tests/unit/test_notify_state_store.py \
                    tests/unit/test_notifier.py \
                    tests/unit/test_notify_orchestrator.py \
                    -v --tb=short
```

---

## Running the Integration Test

Requires a real `DISCORD_WEBHOOK_URL` in the environment:

```bash
DISCORD_WEBHOOK_URL=<your-url> \
STATE_STORE_PATH=./data/test_processed_ids.json \
~/.local/bin/pytest tests/integration/test_sync_notifications.py -v
```

This test creates a temporary state store entry, calls `sync_notifications`,
verifies the Discord message was delivered (via the webhook response), and
verifies the state store was updated. Clean up any test entries from
`#deal_alerts` manually after the run.
