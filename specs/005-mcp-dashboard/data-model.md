# Data Model: OpenClaw MCP Gateway + Dashboard

**Branch**: `005-mcp-dashboard` | **Date**: 2026-07-23

---

## Entities

### GatewayStatus

Runtime state of the OpenClaw gateway process. Returned by the `get_gateway_status` MCP tool and powers `openclaw gateway status`.

| Field | Type | Description |
|-------|------|-------------|
| `running` | bool | `True` if the gateway HTTP server is accepting requests |
| `uptime_seconds` | int \| None | Seconds since gateway start; `None` if stopped |
| `version` | str | Gateway package version (from `__version__`) |
| `host` | str | Bind address (e.g. `"127.0.0.1"`) |
| `port` | int | Bind port (e.g. `18789`) |
| `last_cycle_at` | str \| None | ISO-8601 UTC of most recent completed cycle; `"never"` if none |
| `cycle_running` | bool | `True` if a pipeline cycle is currently in progress |

**Source**: In-process state tracked by `gateway.server` module (start time stored at process boot).

---

### PipelineCycle

One completed pipeline run, read from `pipeline.log` (one JSON line per cycle).

| Field | Type | Description |
|-------|------|-------------|
| `ts` | str | ISO-8601 UTC cycle completion timestamp |
| `emails_processed` | int | Count from step 1 `processed_count` |
| `crm_logged` | int | Count from step 2 result |
| `notified` | int | Count from step 3 result |
| `pending` | int | `crm_pending + notify_pending` at cycle end |
| `errors` | list[str] | Canonical error tokens (at most once each per cycle) |
| `duration_seconds` | float \| None | Elapsed time if available; `None` for log lines lacking it |

**Source**: `pipeline.log` — each line is a JSON object matching this schema. Read by `readers.read_pipeline_log(n)`.

**State transitions**: PipelineCycle records are immutable once written; the log is append-only.

---

### DealRecord

A single deal email captured from the inbox. Derived from entries in `processed_ids.json` where `outcome == "deal_extracted"`.

| Field | Type | Description |
|-------|------|-------------|
| `gmail_message_id` | str | Primary key |
| `processed_at` | str | ISO-8601 UTC when classified as a deal |
| `sender_name` | str | From deal payload |
| `sender_email` | str | From deal payload |
| `subject` | str | From deal payload |
| `deal_type` | str | Classification result (e.g. `"partnership"`) |
| `confidence_score` | float | Gemini classification confidence 0.0–1.0 |
| `crm_status` | str \| None | `"logged"`, `"pending"`, `"failed"`, or `None` (pre-step-2) |
| `crm_retry_count` | int | Number of CRM retry attempts |
| `hubspot_deal_id` | str \| None | HubSpot deal ID if CRM-logged; else `None` |
| `notify_status` | str \| None | `"sent"`, `"pending"`, `"failed"`, or `None` (pre-step-3) |
| `notify_retry_count` | int | Number of notification retry attempts |

**Source**: `processed_ids.json` — entries with `outcome == "deal_extracted"`. Read by `readers.read_deals(limit, status_filter)`.

**Filtering**: `get_deals(status="crm_pending")` returns only deals where `crm_status == "pending"`.

---

### QuotaUsage

Estimated Gemini API usage derived from the cycle log. Not a live API call — computed from `pipeline.log`.

| Field | Type | Description |
|-------|------|-------------|
| `estimated_requests_today` | int | Sum of `emails_processed` across all cycles in the current UTC calendar day |
| `daily_free_tier_limit` | int | Hardcoded constant: `1500` (Gemini 2.5 Flash free-tier RPD) |
| `estimated_remaining` | int | `daily_free_tier_limit - estimated_requests_today` (floored at 0) |
| `pct_used` | float | `estimated_requests_today / daily_free_tier_limit * 100`, capped at 100 |
| `window_date` | str | UTC date (YYYY-MM-DD) the estimate covers |
| `cycles_today` | int | Number of pipeline cycles completed on `window_date` |
| `has_quota_error_today` | bool | `True` if any cycle today logged `"quota_exhausted"` token |

**Note**: One Gemini request per classified email, so `emails_processed` is a reasonable proxy for RPD usage. The estimate may undercount if multiple retries counted separately.

---

### HealthCheckReport

Per-component diagnostic result returned by `get_health` MCP tool and displayed by `openclaw doctor`.

| Field | Type | Description |
|-------|------|-------------|
| `overall` | str | `"HEALTHY"` (all pass) or `"DEGRADED"` (≥1 fail) |
| `components` | list[HealthComponent] | One entry per checked component |
| `checked_at` | str | ISO-8601 UTC of when the check ran |
| `duration_ms` | int | Total time taken for all checks |

#### HealthComponent

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Component name: `"gmail_oauth"`, `"gemini_api"`, `"hubspot_token"`, `"discord_webhook"`, `"state_store"` |
| `status` | str | `"PASS"` or `"FAIL"` |
| `latency_ms` | int \| None | Round-trip latency for network checks; `None` for local checks |
| `message` | str \| None | Human-readable failure reason; `None` on pass |

**Checks performed**:

| Component | Check | Pass Condition |
|-----------|-------|----------------|
| `gmail_oauth` | Load credentials file + attempt token refresh | Token present and refreshable without browser |
| `gemini_api` | Send minimal API request (list models or similar) | HTTP 200 response |
| `hubspot_token` | GET `/crm/v3/properties/deals` with token | HTTP 200 (not 401) |
| `discord_webhook` | HEAD or GET on webhook URL | HTTP 200/204 (not 4xx) |
| `state_store` | Check `STATE_STORE_PATH` is readable and valid JSON | File exists, valid JSON, no lock held |

---

### GatewayConfig

Immutable dataclass read from environment at gateway startup. All validation done in `load_gateway_config()`; `sys.exit(1)` on any violation.

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `host` | str | `"127.0.0.1"` | Non-empty, valid bind address |
| `port` | int | `18789` | Integer 1024–65535 |
| `scheduler_mode` | str | `"gateway"` | `"gateway"`, `"loop"`, or `"systemd"` |
| `poll_interval_minutes` | int | `15` | ≥ 1 (used in `gateway` and `loop` modes) |
| `state_store_path` | Path | required | Non-empty `STATE_STORE_PATH` env var |
| `log_path` | Path | `<state_dir>/pipeline.log` | Non-empty |
| `lock_timeout_minutes` | int | `30` | ≥ 1 |
| `max_pending_retries` | int | `10` | ≥ 1 |
| `log_max_bytes` | int | `10485760` | ≥ 1 |
| `log_backup_count` | int | `3` | ≥ 0 |

**New env vars** (added by this feature):

| Env Var | Default | Maps to |
|---------|---------|---------|
| `GATEWAY_HOST` | `127.0.0.1` | `GatewayConfig.host` |
| `GATEWAY_PORT` | `18789` | `GatewayConfig.port` |
| `SCHEDULER_MODE` | `gateway` | `GatewayConfig.scheduler_mode` (extended with `"gateway"` mode) |

All existing env vars (`STATE_STORE_PATH`, `POLL_INTERVAL_MINUTES`, etc.) continue to work unchanged.

---

## State Store Schema (read-only for gateway)

The gateway reads but never writes `processed_ids.json`. Relevant fields per entry:

```json
{
  "gmail_message_id": "abc123",
  "processed_at": "2026-07-23T00:08:28Z",
  "outcome": "deal_extracted",
  "status": "discord-notified",
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
```

Non-deal entries (`outcome != "deal_extracted"`) are excluded from `DealRecord` queries.

---

## Entity Relationships

```
GatewayConfig
  ├── owns GatewayStatus (tracked in-process)
  ├── owns CycleLogger (via log_path) ← reuses pipeline_orchestrator.CycleLogger
  ├── passes to run_cycle() ← calls pipeline_orchestrator.runner.run_cycle()
  └── passed to readers.py which reads:
        ├── processed_ids.json → list[DealRecord]
        └── pipeline.log → list[PipelineCycle] + QuotaUsage

HealthCheckReport
  └── contains list[HealthComponent] (one per external service)

MCP Tools surface:
  get_gateway_status()   → GatewayStatus
  run_cycle()            → PipelineCycle
  get_pipeline_cycles()  → list[PipelineCycle]
  get_deals()            → list[DealRecord]
  get_quota_usage()      → QuotaUsage
  get_health()           → HealthCheckReport
```
