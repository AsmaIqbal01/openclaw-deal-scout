# Data Model: Pipeline Orchestration

**Branch**: `004-pipeline-orchestration` | **Date**: 2026-07-22

---

## Entities

### PipelineConfig

Immutable dataclass read from environment at startup. All validation done in `load_config()`; `sys.exit(1)` on any violation before the first cycle starts.

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `state_store_path` | `Path` | required | Non-empty `STATE_STORE_PATH` |
| `poll_interval_minutes` | `int` | 15 | ≥ 1 |
| `lock_timeout_minutes` | `int` | 30 | ≥ 1 |
| `log_path` | `Path` | `<state_dir>/pipeline.log` | Non-empty |
| `log_max_bytes` | `int` | 10485760 | ≥ 1 |
| `log_backup_count` | `int` | 3 | ≥ 0 |
| `max_pending_retries` | `int` | 10 | ≥ 1 |
| `scheduler_mode` | `str` | `"loop"` | `"loop"` or `"systemd"` |

**Derived property**: `lock_path = state_store_path.parent / ".pipeline.lock"`

---

### CycleLock

File-based exclusive lock preventing concurrent pipeline cycles.

| Attribute | Value |
|-----------|-------|
| **File path** | `<STATE_STORE_DIR>/.pipeline.lock` |
| **Content** | Single ISO-8601 UTC timestamp line (e.g. `2026-07-22T14:30:00Z`) |
| **Created** | `CycleLock.__enter__`: write timestamp then open file |
| **Deleted** | `CycleLock.__exit__`: always in finally — even on exception |
| **Stale criterion** | Timestamp older than `lock_timeout_minutes` from now |
| **Malformed content** | Non-ISO-8601 string → treated as stale; WARN logged with raw content |

**State transitions**:
- Absent → Created (cycle starts)
- Created → Deleted (cycle ends normally or on exception)
- Created (stale) → Deleted then Created (stale lock cleared at next cycle start)

---

### CycleLogEntry

Single INFO-level JSON line emitted at cycle completion (always, even on error). Written to `PIPELINE_LOG_PATH` via `RotatingFileHandler`.

| Field | Type | Description |
|-------|------|-------------|
| `ts` | ISO-8601 UTC string | Cycle completion timestamp |
| `emails_processed` | int | Count from step 1 `processed_count` |
| `crm_logged` | int | Count from step 2 `crm_logged` (new + drained) |
| `notified` | int | Count from step 3 `discord_notified` (new + drained) |
| `pending` | int | `crm_pending + notify_pending` at cycle end |
| `errors` | list[str] | Canonical error tokens (at most once each per cycle) |

**Canonical error tokens**:

| Token | Trigger |
|-------|---------|
| `"quota_exhausted"` | Step 1 raises `RateLimitExhaustedError` |
| `"gmail_oauth_failed"` | Step 1 raises `google.auth.exceptions.RefreshError` or returns `status=="error"` with auth keyword in `error_details` |
| `"state_store_unreadable"` | Step 1 returns `status=="error"` with state store keyword |
| `"lock_creation_failed"` | `.pipeline.lock` cannot be created (permission error) |
| `"crm_suspended"` | Step 2 returns `suspended: true` |
| `"crm_permanent_failure"` | One or more entries received permanent HubSpot 4xx |
| `"notify_permanent_failure"` | One or more entries received permanent Discord 4xx |
| `"network_error"` | Network-level failure with no HTTP response |
| `"pending_promoted_to_failed"` | One or more entries promoted by `MAX_PENDING_RETRIES` |
| `"unhandled_exception"` | Uncaught exception at pipeline boundary |

---

### State Store Extension (processed_ids.json)

The orchestrator adds four optional fields to existing `messages[]` entries. Non-deal entries (`not_a_deal`, `body_absent`, etc.) never receive these fields.

**Extended entry shape**:

```json
{
  "gmail_message_id": "abc123",
  "processed_at": "2026-07-22T14:30:01Z",
  "outcome": "deal_extracted",
  "status": "discord-notified",
  "crm_status": "logged",
  "crm_retry_count": 0,
  "notify_status": "sent",
  "notify_retry_count": 0
}
```

#### `crm_status` field

| Value | Set when |
|-------|---------|
| `"logged"` | Entry `status` is one of `crm-logged`, `crm-logged-notify-pending`, `discord-notified` after step 2 |
| `"pending"` | Entry `status` is `crm-pending` and `crm_retry_count < max_pending_retries` |
| `"failed"` | Entry `status` is `crm-pending` and `crm_retry_count >= max_pending_retries`, OR step 2 reports permanent 4xx |

#### `crm_retry_count` field

- Integer ≥ 0; default 0 if absent
- Incremented by 1 after each drain cycle where step 2 **attempted** the entry and it remained `crm-pending`
- Reset to 0 when entry transitions to `crm_status: "logged"`
- Cycles where step 2 returns `suspended: true` do **not** increment (no attempt was made)
- Cycles that abort before reaching step 2 do **not** increment

#### `notify_status` field

| Value | Set when |
|-------|---------|
| `"sent"` | Entry `status` is `discord-notified` after step 3 |
| `"pending"` | Entry `status` is `crm-logged-notify-pending` and `notify_retry_count < max_pending_retries` |
| `"failed"` | Entry status is `crm-logged-notify-pending` and `notify_retry_count >= max_pending_retries`, OR step 3 reports permanent 4xx |

#### `notify_retry_count` field

Same semantics as `crm_retry_count` but for step 3 drain cycles.

---

## State Transitions

### CRM flow per deal entry

```
deal_extracted
    │
    ▼ step 2 success
crm_status: "logged"   ←─── crm_status: "pending" (transient failure, retry next cycle)
                                    │
                                    ▼ after max_pending_retries attempts
                              crm_status: "failed"  (no further retry)
```

### Notification flow per deal entry

```
(after crm_status: "logged")
    │
    ▼ step 3 success
notify_status: "sent"  ←─── notify_status: "pending" (transient failure, retry next cycle)
                                    │
                                    ▼ after max_pending_retries attempts
                             notify_status: "failed"  (no further retry)
```

---

## Relationships

```
PipelineConfig
  ├── owns CycleLock (via lock_path)
  ├── owns CycleLogger (via log_path, log_max_bytes, log_backup_count)
  └── passed to run_cycle() which:
        ├── uses CycleLock as context manager
        ├── calls check_new_deals_handler() → updates messages[*].outcome
        ├── calls sync_deals_to_crm() → updates messages[*].status (crm path)
        ├── calls sync_notifications() → updates messages[*].status (notify path)
        ├── calls _update_crm_retry() → writes crm_status / crm_retry_count
        ├── calls _update_notify_retry() → writes notify_status / notify_retry_count
        └── calls cycle_logger.emit_cycle_summary() → appends CycleLogEntry
```
