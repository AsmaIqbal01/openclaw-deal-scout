# MCP Tool Contracts: OpenClaw Gateway

**Feature**: `005-mcp-dashboard` | **Date**: 2026-07-23
**Server name**: `openclaw-gateway`
**Transport**: HTTP (`http://127.0.0.1:18789`)

All tools follow the FastMCP `@mcp.tool()` decorator pattern. Return types are JSON-serialisable dicts. Every tool handles exceptions internally and returns `{"error": "<message>"}` rather than raising to the MCP caller.

---

## Tool: `get_gateway_status`

Returns the runtime state of the OpenClaw gateway process.

**Input**: None

**Output** (GatewayStatus dict):

```json
{
  "running": true,
  "uptime_seconds": 3620,
  "version": "0.1.0",
  "host": "127.0.0.1",
  "port": 18789,
  "last_cycle_at": "2026-07-23T00:14:56Z",
  "cycle_running": false
}
```

**Error response**:
```json
{"error": "<reason>"}
```

**Idempotency**: Read-only; safe to call at any frequency.

---

## Tool: `run_cycle`

Triggers one complete pipeline cycle (Gmail → Gemini → HubSpot → Discord) synchronously. Blocks until the cycle completes or fails.

**Input**: None

**Output** (PipelineCycle dict, same schema as `pipeline.log` entries):

```json
{
  "ts": "2026-07-23T12:00:05Z",
  "emails_processed": 5,
  "crm_logged": 1,
  "notified": 1,
  "pending": 0,
  "errors": []
}
```

**Busy response** (cycle already in progress):
```json
{"busy": true, "message": "A pipeline cycle is already running. Try again after it completes."}
```

**Error response**:
```json
{"error": "<reason>", "ts": "<ISO-8601>"}
```

**Idempotency**: Non-idempotent (triggers real pipeline actions). The cycle lock (`CycleLockActiveError`) prevents double-execution. One cycle per call.

**Timeout**: No client-side timeout defined; the cycle runs to completion (typically 1–10 minutes on free-tier Gemini). MCP clients should set a sufficiently long timeout.

---

## Tool: `get_pipeline_cycles`

Returns recent pipeline cycle summaries from `pipeline.log`.

**Input**:
```json
{"limit": 20}
```
- `limit` (int, optional, default 20, max 100): Number of most-recent cycles to return.

**Output**:
```json
{
  "cycles": [
    {
      "ts": "2026-07-23T00:14:56Z",
      "emails_processed": 22,
      "crm_logged": 1,
      "notified": 1,
      "pending": 0,
      "errors": []
    }
  ],
  "total_in_log": 5
}
```

**Empty case** (no cycles yet):
```json
{"cycles": [], "total_in_log": 0}
```

**Idempotency**: Read-only.

---

## Tool: `get_deals`

Returns deal records from the state store.

**Input**:
```json
{"limit": 50, "status": "all"}
```
- `limit` (int, optional, default 50, max 500): Maximum records to return (newest first).
- `status` (str, optional, default `"all"`): Filter — `"all"` | `"crm_pending"` | `"crm_failed"` | `"notify_pending"` | `"notify_failed"` | `"complete"`.

**Output**:
```json
{
  "deals": [
    {
      "gmail_message_id": "19f8ab0ea26e677c",
      "processed_at": "2026-07-23T00:11:25Z",
      "sender_name": "John Smith",
      "sender_email": "john@example.com",
      "subject": "Partnership Opportunity",
      "deal_type": "partnership",
      "confidence_score": 0.92,
      "crm_status": "logged",
      "crm_retry_count": 0,
      "hubspot_deal_id": "337701952242",
      "notify_status": "sent",
      "notify_retry_count": 0
    }
  ],
  "total_deals": 1,
  "filtered_by": "all"
}
```

**Idempotency**: Read-only. Uses shared (read-only) portalocker lock on state store.

---

## Tool: `get_quota_usage`

Returns estimated Gemini API usage for the current UTC calendar day.

**Input**: None

**Output** (QuotaUsage dict):
```json
{
  "estimated_requests_today": 22,
  "daily_free_tier_limit": 1500,
  "estimated_remaining": 1478,
  "pct_used": 1.47,
  "window_date": "2026-07-23",
  "cycles_today": 1,
  "has_quota_error_today": false
}
```

**Idempotency**: Read-only. Computed from `pipeline.log`; not a live Gemini API call.

---

## Tool: `get_health`

Runs a full health check against all five external components.

**Input**: None

**Output** (HealthCheckReport dict):
```json
{
  "overall": "HEALTHY",
  "checked_at": "2026-07-23T12:00:01Z",
  "duration_ms": 3240,
  "components": [
    {
      "name": "gmail_oauth",
      "status": "PASS",
      "latency_ms": 820,
      "message": null
    },
    {
      "name": "gemini_api",
      "status": "PASS",
      "latency_ms": 450,
      "message": null
    },
    {
      "name": "hubspot_token",
      "status": "PASS",
      "latency_ms": 310,
      "message": null
    },
    {
      "name": "discord_webhook",
      "status": "PASS",
      "latency_ms": 180,
      "message": null
    },
    {
      "name": "state_store",
      "status": "PASS",
      "latency_ms": null,
      "message": null
    }
  ]
}
```

**Degraded example** (gmail_oauth fails):
```json
{
  "overall": "DEGRADED",
  "components": [
    {
      "name": "gmail_oauth",
      "status": "FAIL",
      "latency_ms": null,
      "message": "Token refresh failed: invalid_grant. Re-run setup_oauth.py."
    },
    ...
  ]
}
```

**Idempotency**: Makes live network calls to external services. Safe to call repeatedly but each call consumes one request against each external service's rate limits.

**Timeout**: Per-component timeout of 10 seconds; total check completes within ~30 seconds worst case.

---

## CLI Behaviour

### `openclaw gateway status`

Calls `GET http://127.0.0.1:18789/mcp` (or equivalent) to determine if the gateway is up, then calls `get_gateway_status` MCP tool.

**Exit codes**:
- `0` — gateway RUNNING
- `1` — gateway STOPPED or unreachable

**Output format** (stdout):
```
OpenClaw Gateway: RUNNING
  Version : 0.1.0
  Uptime  : 1h 00m 20s
  Host    : 127.0.0.1:18789
  Last run: 2026-07-23T00:14:56Z
  Cycle   : idle
```

---

### `openclaw dashboard`

Opens default browser to `http://127.0.0.1:18789`. If gateway is not reachable, prints error and exits non-zero.

```
Opening OpenClaw dashboard at http://127.0.0.1:18789 ...
```

---

### `openclaw doctor`

Calls `get_health` MCP tool if gateway is running; otherwise runs checks directly (without HTTP).

**Output format** (stdout):
```
OpenClaw Doctor — Health Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  gmail_oauth      PASS   (820ms)
  ✅  gemini_api       PASS   (450ms)
  ✅  hubspot_token    PASS   (310ms)
  ✅  discord_webhook  PASS   (180ms)
  ✅  state_store      PASS   (local)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall: HEALTHY  (3.2s)
```

**Degraded output**:
```
  ❌  gmail_oauth      FAIL   Token refresh failed: invalid_grant. Re-run setup_oauth.py.
```

**Exit codes**:
- `0` — all PASS
- `1` — ≥1 FAIL
