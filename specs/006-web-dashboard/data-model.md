# Data Model: 006-web-dashboard

**Date**: 2026-07-24 | **Branch**: `006-web-dashboard`

These are the JSON shapes the browser receives from the five REST endpoints. All shapes are derived from the existing MCP tool responses (contracts: `specs/005-mcp-dashboard/contracts/mcp-tools.md`). No new data is introduced — the REST layer is a thin adapter.

---

## GatewayStatus

Returned by `GET /api/status` (combines `get_gateway_status` + `get_health`).

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
    "components": [
      {
        "name": "gmail",
        "status": "PASS",
        "latency_ms": 312,
        "message": null
      },
      {
        "name": "gemini",
        "status": "PASS",
        "latency_ms": 188,
        "message": null
      },
      {
        "name": "hubspot",
        "status": "PASS",
        "latency_ms": 421,
        "message": null
      },
      {
        "name": "discord",
        "status": "FAIL",
        "latency_ms": null,
        "message": "Webhook returned 404"
      },
      {
        "name": "state_store",
        "status": "PASS",
        "latency_ms": null,
        "message": null
      },
      {
        "name": "log",
        "status": "PASS",
        "latency_ms": null,
        "message": null
      }
    ],
    "checked_at": "2026-07-24T10:00:00Z",
    "duration_ms": 921
  }
}
```

**Field notes**:
- `gateway.cycle_running`: `true` while a pipeline cycle is active — drives Run Cycle button state.
- `health.overall`: `"HEALTHY"` (all PASS) or `"DEGRADED"` (≥1 FAIL).
- `health.components[].status`: `"PASS"` or `"FAIL"`.
- `health.components[].latency_ms`: `null` for local checks (state_store, log); integer ms for network checks.

---

## CycleList

Returned by `GET /api/cycles?limit=20`.

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
    },
    {
      "ts": "2026-07-23T11:30:02Z",
      "emails_processed": 2,
      "crm_logged": 0,
      "notified": 0,
      "pending": 1,
      "errors": ["quota_exhausted"]
    }
  ],
  "total_in_log": 48
}
```

**Field notes**:
- `cycles`: Ordered newest-first (as returned by `get_pipeline_cycles`).
- `errors`: List of error label strings; empty list `[]` when clean.
- `total_in_log`: Total cycle count in the log file (unfiltered).

---

## DealList

Returned by `GET /api/deals?status=all&limit=50`.

```json
{
  "deals": [
    {
      "message_id": "msg_abc123",
      "subject": "Partnership inquiry — OpenClaw Deal Scout",
      "sender": "partner@example.co.uk",
      "outcome": "deal_extracted",
      "crm_status": "logged",
      "notify_status": "sent",
      "ts": "2026-07-23T09:14:22Z"
    },
    {
      "message_id": "msg_def456",
      "subject": "Re: pricing for SMBs",
      "sender": "founder@startup.pk",
      "outcome": "deal_extracted",
      "crm_status": "pending",
      "notify_status": "pending",
      "ts": "2026-07-23T10:30:00Z"
    }
  ],
  "total_deals": 47,
  "filtered_by": "all"
}
```

**Field notes**:
- `deals`: Newest-first slice, capped at `limit`.
- `crm_status`: one of `"pending"` | `"logged"` | `"failed"`.
- `notify_status`: one of `"pending"` | `"sent"` | `"failed"`.
- `filtered_by`: echoes the requested status filter.
- `total_deals`: Total deal count matching the filter (before limit).

**Valid status filter values**: `"all"` | `"crm_pending"` | `"crm_failed"` | `"notify_pending"` | `"notify_failed"` | `"complete"`

---

## QuotaUsage

Returned by `GET /api/quota`.

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

**Field notes**:
- `pct_used`: Float 0–100 (capped at 100).
- `has_quota_error_today`: `true` if any cycle logged `"quota_exhausted"` today (UTC).
- `window_date`: UTC date string (`YYYY-MM-DD`).

---

## CycleResult

Returned by `POST /api/run-cycle` on completion.

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

**Busy response** (cycle already running):
```json
{
  "busy": true,
  "message": "A pipeline cycle is already running. Try again after it completes."
}
```

**Error response**:
```json
{
  "error": "Connection refused",
  "ts": "2026-07-24T10:05:00Z"
}
```

---

## Error Envelope

When any REST endpoint encounters a server-side error, it returns HTTP 500 with:

```json
{
  "error": "<human-readable message>",
  "endpoint": "/api/status"
}
```

The browser renders this as a per-panel error state (e.g. "Status unavailable — gateway error") rather than crashing the whole page.
