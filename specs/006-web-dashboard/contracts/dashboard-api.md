# Dashboard REST API Contracts: 006-web-dashboard

**Date**: 2026-07-24 | **Branch**: `006-web-dashboard`
**Base URL**: `http://127.0.0.1:18790`

These five endpoints are added to the existing FastMCP gateway as custom Starlette routes. They are thin adapters over the existing MCP tool implementations — no new business logic.

---

## GET /

Returns the dashboard HTML page.

**Response**: `200 OK` — `Content-Type: text/html; charset=utf-8`

Body: full contents of `src/openclaw_gateway/static/dashboard.html`.

**Error**: `500 Internal Server Error` if the HTML file cannot be read.

---

## GET /api/status

Returns combined gateway status and health check.

**Response**: `200 OK` — `Content-Type: application/json`

```json
{
  "gateway": {
    "running": true,
    "uptime_seconds": 3620,
    "version": "0.1.0",
    "host": "127.0.0.1",
    "port": 18790,
    "last_cycle_at": "2026-07-23T00:14:56Z",
    "cycle_running": false
  },
  "health": {
    "overall": "HEALTHY",
    "components": [ ... ],
    "checked_at": "2026-07-24T10:00:00Z",
    "duration_ms": 921
  }
}
```

**Implementation**: calls `get_gateway_status(config)` and `get_health(config)` from `openclaw_gateway.tools.status`, combines into one response object.

**Idempotency**: Read-only. Safe to poll at any frequency.

---

## GET /api/cycles

Returns recent pipeline cycle summaries.

**Query parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | `20` | Max cycles to return (1–100) |

**Response**: `200 OK` — `Content-Type: application/json`

```json
{
  "cycles": [
    {
      "ts": "2026-07-23T12:00:05Z",
      "emails_processed": 5,
      "crm_logged": 1,
      "notified": 1,
      "pending": 0,
      "errors": []
    }
  ],
  "total_in_log": 48
}
```

**Implementation**: delegates to `get_pipeline_cycles(limit=limit)` from `openclaw_gateway.tools.pipeline`.

**Idempotency**: Read-only.

---

## GET /api/deals

Returns detected deals with optional status filter.

**Query parameters**:

| Parameter | Type | Default | Valid values |
|-----------|------|---------|--------------|
| `status` | string | `"all"` | `all` \| `crm_pending` \| `crm_failed` \| `notify_pending` \| `notify_failed` \| `complete` |
| `limit` | integer | `50` | 1–500 |

**Response**: `200 OK` — `Content-Type: application/json`

```json
{
  "deals": [
    {
      "message_id": "msg_abc123",
      "subject": "Partnership inquiry",
      "sender": "partner@example.co.uk",
      "outcome": "deal_extracted",
      "crm_status": "logged",
      "notify_status": "sent",
      "ts": "2026-07-23T09:14:22Z"
    }
  ],
  "total_deals": 47,
  "filtered_by": "all"
}
```

**Invalid `status` value**: returns `400 Bad Request`:
```json
{"error": "Invalid status filter. Valid values: all, crm_pending, crm_failed, notify_pending, notify_failed, complete"}
```

**Implementation**: delegates to `get_deals(limit=limit, status=status)` from `openclaw_gateway.tools.pipeline`.

**Idempotency**: Read-only.

---

## GET /api/quota

Returns Gemini API quota usage for the current UTC day.

**Response**: `200 OK` — `Content-Type: application/json`

```json
{
  "estimated_requests_today": 342,
  "daily_free_tier_limit": 1500,
  "estimated_remaining": 1158,
  "pct_used": 22.8,
  "window_date": "2026-07-24",
  "cycles_today": 12,
  "has_quota_error_today": false
}
```

**Implementation**: delegates to `get_quota_usage()` from `openclaw_gateway.tools.pipeline`.

**Idempotency**: Read-only.

---

## POST /api/run-cycle

Triggers one complete pipeline cycle synchronously.

**Request body**: none (empty POST body is accepted).

**Response on success** — `200 OK`:
```json
{
  "ts": "2026-07-24T10:05:12Z",
  "emails_processed": 3,
  "crm_logged": 1,
  "notified": 1,
  "pending": 0,
  "errors": []
}
```

**Response when busy** — `200 OK` (not a 4xx; browser should show "busy" message):
```json
{
  "busy": true,
  "message": "A pipeline cycle is already running. Try again after it completes."
}
```

**Response on error** — `200 OK` (errors surfaced in body, not HTTP status):
```json
{
  "error": "<reason>",
  "ts": "2026-07-24T10:05:00Z"
}
```

**Implementation**: delegates to `run_cycle()` from `openclaw_gateway.tools.pipeline`. The cycle lock prevents double-execution.

**Idempotency**: Non-idempotent. Triggers real pipeline actions (Gmail read, Gemini calls, HubSpot writes, Discord POST). The pipeline lock prevents concurrent execution.

**Client behaviour**: Browser must disable the Run Cycle button immediately on click, poll `/api/status` every 2 seconds for `cycle_running` status, and re-enable the button when `cycle_running` returns `false`. A 90-second client-side timeout shows a "still running — check pipeline.log" message without terminating the cycle.

---

## CORS

All `/api/*` endpoints return:
```
Access-Control-Allow-Origin: *
```
Required for browser fetch from `http://127.0.0.1:18790` to itself (same-origin, but explicit header prevents browser CORS errors in some configurations).

---

## Error Envelope (all endpoints)

```json
{
  "error": "<human-readable description>",
  "endpoint": "/api/<name>"
}
```

HTTP 500 for server-side failures. The browser renders per-panel error states rather than crashing the full page.
