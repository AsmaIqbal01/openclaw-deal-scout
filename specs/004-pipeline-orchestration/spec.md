# Feature Specification: Pipeline Orchestration, Error Handling & End-to-End Wiring

**Feature Branch**: `004-pipeline-orchestration`
**Created**: 2026-07-22
**Status**: Draft
**Input**: Step 4 of 4 — Automate the full OpenClaw Deal Scout pipeline end-to-end with scheduling, cross-step error handling, and operational logging.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Fully Automated Deal Pipeline (Priority: P1)

An operator sets up OpenClaw once and leaves it running. When a deal email arrives in their Gmail inbox, the system automatically detects it, logs it to HubSpot, and posts a Discord alert — all without the operator doing anything.

**Why this priority**: This is the core product promise ("Digital FTE"). Without automatic scheduling and end-to-end wiring, the three existing steps are only useful when manually triggered, which defeats the purpose of the tool.

**Independent Test**: Trigger the orchestrator on a schedule with a new deal email present in the inbox. Confirm that a HubSpot deal and Discord notification appear within one polling interval, with no operator action.

**Acceptance Scenarios**:

1. **Given** the orchestrator is running on its configured schedule and a new deal email has arrived unread in the inbox, **When** the next scheduled cycle fires, **Then** the email is classified, a HubSpot deal is created, and a Discord alert is posted — all within that single cycle, with no manual tool invocation.
2. **Given** the orchestrator is running and the inbox contains no new deal emails, **When** a cycle fires, **Then** the cycle completes with zero CRM entries and zero Discord notifications, and the orchestrator remains running for the next cycle.
3. **Given** the orchestrator is running on a machine that was rebooted, **When** the machine comes back up, **Then** the orchestrator resumes scheduling automatically without operator input.
4. **Given** `POLL_INTERVAL_MINUTES` is set to 15, **When** a cycle completes, **Then** the next cycle fires within 1 minute of the configured interval (i.e., between minute 14 and 16 from the previous cycle start).

---

### User Story 2 — Concurrent Cycle Prevention (Priority: P2)

If a pipeline cycle is slow (e.g., many emails to classify), the scheduler must not start a second overlapping cycle that could corrupt state or send duplicate notifications.

**Why this priority**: Concurrent cycles interleave state-store writes and risk duplicate HubSpot deals and Discord pings — a direct violation of the idempotency promise.

**Independent Test**: Trigger the orchestrator twice in rapid succession while a long cycle is still in progress. Confirm the second trigger is silently rejected and the first cycle completes cleanly.

**Acceptance Scenarios**:

1. **Given** a pipeline cycle is currently in progress, **When** the scheduler fires again before the current cycle has finished, **Then** the new trigger is rejected without starting a second cycle, and the in-progress cycle completes normally.
2. **Given** a previous cycle was interrupted mid-run (e.g., by a crash), **When** the orchestrator restarts and a new cycle fires, **Then** any stale lock (older than `LOCK_TIMEOUT_MINUTES`) is detected and cleared so the new cycle can proceed.
3. **Given** a stale lock is cleared at cycle start, **When** the operator reads the log, **Then** a WARN-level entry records the stale lock detection and clearance, including the lock's creation timestamp.

---

### User Story 3 — Quota and Transient Error Resilience (Priority: P3)

When an external service (Gemini, HubSpot, Discord) is temporarily unavailable or rate-limited, the orchestrator handles the failure cleanly: it logs what happened, does not crash, and picks up where it left off on the next cycle.

**Why this priority**: The Gemini free tier has a fixed daily classification quota. Exhausting it mid-cycle must not stop future cycles from running or leave the state store in a bad state.

**Independent Test**: Exhaust the Gemini daily quota, then trigger a cycle with a new deal email. Confirm the orchestrator logs the quota error and exits the cycle cleanly. Confirm the next scheduled cycle (after quota reset) processes the email successfully.

**Acceptance Scenarios**:

1. **Given** the Gemini daily classification quota is exhausted mid-cycle, **When** the orchestrator encounters the quota error, **Then** it logs the specific quota exhaustion event at ERROR level, stops attempting further classification calls in that cycle, and exits cleanly without leaving any stale lock or corrupt state store entry.
2. **Given** a HubSpot write fails during a cycle (e.g., 503), **When** the cycle completes, **Then** the affected deal's `crm_status` field in the state store is set to `"pending"`, the cycle exits cleanly, and the next scheduled cycle retries the CRM write automatically without any special operator action.
3. **Given** a Discord notification fails during a cycle, **When** the cycle completes, **Then** the affected deal's `notify_status` field is set to `"pending"`, the cycle exits cleanly, and the next cycle retries the notification.
4. **Given** an unhandled exception occurs anywhere in the cycle, **When** the exception is raised, **Then** it is caught at the pipeline boundary, logged at ERROR level with full traceback, the cycle lock is released, and the orchestrator remains running for the next scheduled cycle.
5. **Given** the Gmail OAuth token has expired and the automatic refresh attempt also fails, **When** step 1 attempts to connect, **Then** the orchestrator logs the token failure at ERROR level, aborts the current cycle cleanly (no lock left, no state corruption), and retries on the next scheduled cycle.
6. **Given** the state store file is missing or corrupt at cycle start, **When** the orchestrator attempts to read it, **Then** it logs the read failure at ERROR level and aborts the cycle cleanly — it does not overwrite or truncate the file; the file is left as-is for manual recovery.

---

### User Story 4 — Operational Log Visibility (Priority: P4)

After each cycle, an operator can read a single log line summarising what happened — how many emails were processed, how many deals were logged, how many notifications were sent, and whether any errors occurred — without having to re-run any tool.

**Why this priority**: An unattended agent that logs nothing gives the operator no way to know it is working. Clear cycle summaries make health checks possible from the log file alone.

**Independent Test**: Run a cycle and read the log output. Confirm a single summary JSON line is present with all required fields and correct values.

**Acceptance Scenarios**:

1. **Given** a cycle has completed successfully, **When** the operator reads the log, **Then** exactly one INFO-level cycle summary JSON line is present with these fields: `ts` (ISO-8601), `emails_processed` (int), `crm_logged` (int), `notified` (int), `pending` (int), `errors` (list of strings, empty if none).
2. **Given** a cycle encountered one or more errors, **When** the operator reads the log, **Then** each error appears as an ERROR-level line with: error type, affected email ID or step name, and a human-readable description sufficient to diagnose without re-running anything.
3. **Given** the orchestrator has been running for multiple cycles, **When** the operator reads the log, **Then** log entries from older cycles are still accessible and the log file has not grown without bound (rotation or size cap in effect per `LOG_MAX_BYTES`).
4. **Given** a DEBUG-level log entry is written, **When** an INFO-level entry occurs in the same cycle, **Then** INFO entries are visually distinct in the log and no DEBUG output is present in the INFO stream (severity levels must not be mixed).
5. **Given** the zero-cost constraint in FR-002, **When** the orchestrator is deployed, **Then** no log entry references a paid external logging service (all logging is local file-based).

---

---

### User Story 5 — Startup Guard and Retry Limits (Priority: P5)

The orchestrator must refuse to run if its required configuration is missing, must handle filesystem failures around its own lock file, and must not retry permanently-broken entries forever.

**Why this priority**: A misconfigured orchestrator that silently starts and crashes mid-cycle is harder to diagnose than one that fails at startup with a clear message. Permanent errors (bad deal data, revoked credentials) that loop as `"pending"` indefinitely waste API quota and obscure the real failure.

**Independent Test**: Start the orchestrator with `STATE_STORE_PATH` unset; confirm it exits immediately with a non-zero code. Inject an HTTP 401 HubSpot failure; confirm `crm_status` is set to `"failed"`, not `"pending"`. Simulate `MAX_PENDING_RETRIES` drain cycles; confirm the entry is promoted to `"failed"`.

**Acceptance Scenarios**:

1. **Given** `STATE_STORE_PATH` is absent or empty in the environment, **When** the orchestrator process starts, **Then** it exits immediately with a non-zero exit code and prints a clear error message — no cycle is attempted and no `.pipeline.lock` file is created.
2. **Given** the state-store directory has filesystem permissions that prevent file creation, **When** a cycle trigger fires, **Then** the lock-file creation attempt fails with a permission error, the cycle is skipped with an ERROR log entry naming the permission failure, and the orchestrator process remains alive for the next scheduled cycle.
3. **Given** a HubSpot write fails with HTTP 401 (permanent, unauthorized) during a cycle, **When** the cycle completes, **Then** `crm_status` for that entry is set to `"failed"` (not `"pending"`), an ERROR log entry is written, and that entry does not appear in any future automatic drain pass.
4. **Given** an entry's `crm_status` has been `"pending"` for `MAX_PENDING_RETRIES` drain-eligible cycles (cycles where step 2 runs and the entry is eligible to drain), **When** the next drain pass runs, **Then** the entry's `crm_status` is promoted to `"failed"`, a WARN log entry is written containing the entry's `gmail_message_id`, and the entry is excluded from all future automatic retry.
5. **Given** step 2 returns `suspended: true` (HubSpot circuit breaker active), **When** the orchestrator processes the result, **Then** it logs a WARN entry, proceeds to run step 3 normally, and emits a cycle summary log line that includes `"crm_suspended"` in the `errors` list — the orchestrator process is not terminated.
6. **Given** `POLL_INTERVAL_MINUTES` is set to a non-numeric value (e.g., `"abc"`) at orchestrator startup, **When** the orchestrator starts, **Then** it exits with a non-zero exit code, prints a message identifying `POLL_INTERVAL_MINUTES` and its valid range, creates no lock file, and runs no cycle.
7. **Given** `.pipeline.lock` exists but contains non-ISO-8601 content (e.g., an empty file or a truncated timestamp), **When** a cycle trigger fires, **Then** the malformed lock is treated as stale: a WARN log entry is written noting the parse failure and raw content, the lock file is deleted, and the new cycle proceeds normally.
8. **Given** step 1 has already classified 2 emails (written to state store) before the Gemini daily quota is exhausted mid-batch, **When** the quota error fires, **Then** the orchestrator still runs step 2 and step 3 for the 2 already-classified entries in that same cycle before exiting cleanly, so those entries reach `crm_status: "logged"` and `notify_status: "sent"` within the same cycle.

---

### Edge Cases

- **All emails already processed**: Running against a fully-processed inbox produces zero new HubSpot deals and zero new Discord notifications (full idempotency).
- **Missing/corrupt state store**: Cycle aborts cleanly at read time; file is not modified or truncated; ERROR log entry written.
- **Gmail OAuth token expired with failed refresh**: Cycle aborts cleanly after authentication failure; ERROR log entry written; next cycle retries normally.
- **Machine clock skew**: If the system clock moves backward (e.g., NTP correction), `last_poll_time` stored as ISO-8601 in the state store prevents re-polling already-seen windows; if the clock jumps forward, the next poll window starts from the stored `last_poll_time`, not the skewed "now".
- **SIGKILL mid-cycle (no graceful shutdown)**: Partial state (some deals `crm_status: "logged"`, others still `"pending"`) is left in the store. On next cycle, the drain pass picks up all `"pending"` entries and processes them; no manual recovery needed provided the state store file is not truncated.
- **SIGTERM mid-cycle (graceful stop from systemd)**: systemd sends SIGTERM before SIGKILL on `systemctl stop` or service restart. CPython's default SIGTERM handler calls `os._exit()`, bypassing `finally` blocks and orphaning `.pipeline.lock`. FR-023 mandates a SIGTERM handler that completes the current step, releases the lock, and exits cleanly. Residual state is the same as SIGKILL (pending entries drained by next cycle).
- **Step 1 succeeds but step 2 partially fails mid-batch**: Entries successfully CRM-logged have `crm_status: "logged"`; failed entries have `crm_status: "pending"`. The cycle continues processing remaining entries; the next cycle drains pending ones.
- **Log rotation race**: If log rotation fires while the orchestrator is writing a summary line, the line must not be silently dropped; the rotation strategy must be atomic with respect to active write handles.
- **Invalid env var values at startup**: If `POLL_INTERVAL_MINUTES=abc` or `LOCK_TIMEOUT_MINUTES=0`, the orchestrator must refuse to start with a clear error — no partial cycle should begin with an invalid interval.
- **Malformed lock file content**: If `.pipeline.lock` exists but contains a non-ISO-8601 string (truncated write, empty file, bit-flip), the content cannot be used to evaluate staleness — it must be treated as stale and cleared rather than blocking all future cycles.
- **Partially-classified batch after Gemini quota abort**: Step 1 classifies emails sequentially and writes each result to the state store as it goes. When `RateLimitExhaustedError` is raised mid-batch, some emails are already in the store as `deal_extracted`. Steps 2 and 3 must still run for those entries in the same cycle so they are not left dangling until the next cycle's natural drain pass.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST automatically trigger the full pipeline (steps 1 → 2 → 3 in sequence) on a recurring schedule controlled by the `POLL_INTERVAL_MINUTES` environment variable (default: 15) without any operator action after initial setup.
- **FR-002**: The scheduling mechanism MUST be zero-cost: no paid job scheduler, hosted cron service, or external paid dependency. Acceptable mechanisms: cron, systemd timer, or a native sleep-loop.
- **FR-003**: The system MUST prevent concurrent pipeline cycles using a lock file named `.pipeline.lock` in the state store directory. If the lock file exists and is not stale (creation timestamp < `LOCK_TIMEOUT_MINUTES` ago), the new trigger MUST be rejected; the in-progress cycle MUST complete unaffected.
- **FR-004**: If `.pipeline.lock` exists and its creation timestamp is older than `LOCK_TIMEOUT_MINUTES` (default: 30), the lock is considered stale. The next cycle MUST log a WARN entry with the lock's creation timestamp, delete the stale lock, and proceed normally.
- **FR-005**: When the Gemini daily classification quota is exhausted mid-cycle (HTTP 429 with `GenerateRequestsPerDayPerProjectPerModel-FreeTier` quota metric), the system MUST log the specific quota error at ERROR level, stop further classification attempts in that cycle, and exit cleanly — the `.pipeline.lock` must be released and no state store entry must be left corrupt or incomplete.
- **FR-006**: When a CRM write (step 2) fails transiently for a given deal entry, the system MUST set `crm_status: "pending"` on that entry in the state store and continue processing remaining entries in the cycle. The next cycle's step 2 pass MUST retry all entries where `crm_status == "pending"`.
- **FR-007**: When a Discord notification (step 3) fails transiently for a given deal entry, the system MUST set `notify_status: "pending"` on that entry and continue. The next cycle's step 3 pass MUST retry all entries where `notify_status == "pending"`.
- **FR-008**: Unhandled exceptions at the pipeline boundary MUST be caught, logged at ERROR level with full traceback, the `.pipeline.lock` released, and the orchestrator process MUST remain running for the next scheduled cycle.
- **FR-009**: Each completed cycle MUST emit exactly one INFO-level JSON summary line with fields: `ts` (ISO-8601 string), `emails_processed` (int), `crm_logged` (int), `notified` (int), `pending` (int), `errors` (list of strings). `crm_logged` MUST count ALL entries that transitioned to `crm_status: "logged"` during this cycle's step 2 pass — including both newly-classified entries logged for the first time and previously-pending entries that were successfully drained in this same cycle. Similarly, `notified` counts all entries that transitioned to `notify_status: "sent"` in step 3 this cycle, regardless of whether they were new or previously pending. `pending` counts all entries whose `crm_status` or `notify_status` remains `"pending"` at cycle end.
- **FR-010**: Log output MUST use these severity levels: DEBUG for cycle start/end detail; INFO for the cycle summary and per-deal events; WARN for stale locks, retries, and skips; ERROR for failures requiring operator attention.
- **FR-011**: Log files MUST be size-bounded using `LOG_MAX_BYTES` (default: 10 MB) with rotation keeping the last 3 backup files. The rotation mechanism must be atomic with respect to active write handles.
- **FR-012**: Running the orchestrator against an inbox where all deals have already been fully processed MUST result in zero new HubSpot deals and zero new Discord notifications.
- **FR-013**: The orchestrator MUST start automatically on machine reboot without operator input, consistent with Principle III (headless/unattended operation).
- **FR-014**: If the Gmail OAuth token has expired and the automatic refresh attempt also fails, the orchestrator MUST log the failure at ERROR level and abort the current cycle cleanly — `.pipeline.lock` released, state store untouched — then retry on the next scheduled cycle.
- **FR-015**: If the state store file is missing or unreadable at cycle start, the orchestrator MUST log the failure at ERROR level and abort the cycle cleanly — it MUST NOT overwrite, truncate, or recreate the state store file without operator confirmation.
- **FR-016**: If `STATE_STORE_PATH` is absent or empty in the environment at orchestrator startup (before any cycle runs), the orchestrator MUST refuse to start and exit with a non-zero exit code and a clear error message — it MUST NOT attempt to run any cycle with an undefined state store path.
- **FR-017**: If the `.pipeline.lock` file cannot be created due to a filesystem permission error, the orchestrator MUST log the failure at ERROR level and skip the cycle (do not proceed without a lock). If the lock file cannot be deleted at cycle end, the orchestrator MUST log a WARN entry but MUST NOT terminate the process. Recovery timeline: because FR-004 requires the lock's creation timestamp to be older than `LOCK_TIMEOUT_MINUTES` before the lock is treated as stale, a lock whose deletion failed will cause all subsequent scheduled cycle triggers to be rejected as "active lock present" until at least `LOCK_TIMEOUT_MINUTES` minutes have elapsed since the lock was originally created. This may span two or more full poll intervals if `LOCK_TIMEOUT_MINUTES` exceeds `POLL_INTERVAL_MINUTES`. The first cycle that fires after `LOCK_TIMEOUT_MINUTES` minutes have elapsed from the lock's creation timestamp will detect the stale lock via FR-004, clear it, and proceed normally. Operators should set `LOCK_TIMEOUT_MINUTES` with this gap in mind (recommended: ≥ 2× `POLL_INTERVAL_MINUTES`).
- **FR-018**: HubSpot and Discord write failures MUST be classified as transient (HTTP 429, 500-504 → `"pending"`, retry next cycle) or permanent (HTTP 400, 401, 403, 404 → `"failed"`, no automatic retry, ERROR log). Permanent failures require operator inspection; they MUST NOT be retried automatically.
- **FR-019**: A `"pending"` entry that has not been resolved after `MAX_PENDING_RETRIES` consecutive cycles MUST be promoted to `"failed"` status, logged at WARN level with the entry's `gmail_message_id`, and excluded from future automatic retry.
- **FR-020**: At orchestrator startup (before any cycle runs), the orchestrator MUST validate all numeric environment variables. If any required variable is missing, non-numeric, or out of its valid range (see table below), the orchestrator MUST exit with a non-zero exit code and a message identifying the invalid variable and its valid range. No cycle may start with invalid configuration.

  | Variable | Valid range |
  |---|---|
  | `POLL_INTERVAL_MINUTES` | Integer ≥ 1 |
  | `LOCK_TIMEOUT_MINUTES` | Integer ≥ 1 |
  | `LOG_MAX_BYTES` | Integer ≥ 1 |
  | `LOG_BACKUP_COUNT` | Integer ≥ 0 |
  | `MAX_PENDING_RETRIES` | Integer ≥ 1 |

- **FR-021**: If the `.pipeline.lock` file exists but its content cannot be parsed as a valid ISO-8601 timestamp (e.g., empty file, truncated write, or corrupt content), the lock MUST be treated as stale: log a WARN entry noting the parse failure and the raw file content (truncated to 100 chars), delete the lock file, and proceed with the cycle normally.
- **FR-022**: When step 1 (`check_new_deals_handler`) raises `RateLimitExhaustedError` mid-batch (some emails already classified and written to the state store before the error), the orchestrator MUST still invoke step 2 (`sync_deals_to_crm`) and step 3 (`sync_notifications`) for those already-classified entries before exiting the cycle. Step 1's quota error aborts further classification attempts in that cycle only — it does not skip the CRM and notification drain for work already completed in that same cycle.
- **FR-023**: The orchestrator MUST install a SIGTERM signal handler at startup. When SIGTERM is received, the handler MUST: (a) set a shutdown flag that prevents new cycles from starting, (b) allow the current in-progress cycle to complete its current atomic step (a single step 1, 2, or 3 invocation), (c) release `.pipeline.lock` via the same `finally` block used for normal cycle exit, and (d) exit with code 0. Partial state after SIGTERM is identical to partial state after SIGKILL — the next cycle's drain pass recovers all `"pending"` entries. **Rationale**: CPython's default SIGTERM disposition calls `os._exit()` at the C level, bypassing `finally` blocks and leaving `.pipeline.lock` orphaned on every `systemctl stop` or service restart. Without a SIGTERM handler, every clean service stop would block subsequent cycles for up to `LOCK_TIMEOUT_MINUTES` minutes.

### Key Entities

- **Pipeline Cycle**: One scheduled execution of steps 1 → 2 → 3. Has a start time, completion status, and a summary of outcomes per step.
- **Cycle Lock**: A file named `.pipeline.lock` written to the state store directory at cycle start and deleted at cycle end (normal or error). Contains the cycle start timestamp in ISO-8601 format. Considered stale if older than `LOCK_TIMEOUT_MINUTES`.
- **Cycle Log Entry**: A single INFO-level JSON line emitted at cycle completion with fields `ts`, `emails_processed`, `crm_logged`, `notified`, `pending`, `errors`.
- **Pending State Fields**: Two new optional fields added to each `messages` entry in `processed_ids.json`:
  - `crm_status`: `"logged"` (CRM write succeeded), `"pending"` (transient failure; retry next cycle), or `"failed"` (permanent failure or retry limit reached; no automatic retry). Absent on entries that are not deals.
  - `notify_status`: `"sent"` (Discord notification succeeded), `"pending"` (transient failure; retry next cycle), or `"failed"` (permanent failure or retry limit reached; no automatic retry). Absent on entries where Discord has not been attempted.

### Interface Contracts

#### State Store Schema Extension

Existing entries in `processed_ids.json` → `messages[]` gain two optional fields when the orchestrator processes them:

```json
{
  "gmail_message_id": "...",
  "outcome": "deal_extracted",
  "status": "...",
  "crm_status": "logged | pending | failed",
  "notify_status": "sent | pending | failed"
}
```

`crm_status` is written by step 2; `notify_status` is written by step 3. Non-deal entries (`outcome: "not_a_deal"`, `"rate_limited"`, etc.) never receive these fields. The orchestrator never modifies any other existing field.

**Canonical `errors` list values** (the `errors` field in the cycle summary JSON is a list of zero or more of these string tokens):

| Token | Emitted when |
|---|---|
| `"quota_exhausted"` | Step 1 raises `RateLimitExhaustedError` (Gemini daily quota hit) |
| `"gmail_oauth_failed"` | Step 1 raises `google.auth.exceptions.RefreshError` |
| `"state_store_unreadable"` | State store file is missing or unreadable at cycle start |
| `"lock_creation_failed"` | `.pipeline.lock` cannot be created (filesystem permission error) |
| `"crm_suspended"` | Step 2 returns `suspended: true` (HubSpot circuit breaker active) |
| `"crm_permanent_failure"` | One or more deal entries received a permanent HubSpot HTTP error (4xx) |
| `"notify_permanent_failure"` | One or more entries received a permanent Discord HTTP error (4xx) |
| `"network_error"` | One or more entries hit a network-level failure (no HTTP response received) for HubSpot or Discord |
| `"pending_promoted_to_failed"` | One or more entries were promoted from `"pending"` to `"failed"` by FR-019 |
| `"unhandled_exception"` | An uncaught exception was caught at the pipeline boundary (FR-008) |

Multiple tokens may appear in the same cycle's `errors` list. Each token appears **at most once** per cycle regardless of how many entries triggered it (e.g., 5 permanent HubSpot failures produce one `"crm_permanent_failure"` token, not five). An empty list (`[]`) means the cycle completed with no errors or warnings.

#### Cycle Lock File

- **Path**: `<STATE_STORE_DIR>/.pipeline.lock`
- **Content**: Single line containing an ISO-8601 timestamp in UTC with the `Z` suffix (e.g., `2026-07-22T14:30:00Z`). Timezone-naive datetimes are not acceptable — all lock timestamps must be UTC-explicit so staleness comparisons are unambiguous across system timezone changes.
- **Lifecycle**: Created at cycle start (before any step executes); deleted at cycle end (in a `finally` block guaranteeing deletion on error as well as on success)
- **Staleness criterion**: If the timestamp in the file is older than `LOCK_TIMEOUT_MINUTES` minutes from now, the lock is stale

#### Cycle Log Entry (JSON)

```json
{
  "ts": "2026-07-22T14:30:05Z",
  "emails_processed": 3,
  "crm_logged": 1,
  "notified": 1,
  "pending": 0,
  "errors": []
}
```

Field semantics:
- `crm_logged`: count of entries that transitioned to `crm_status: "logged"` this cycle (new + drained from pending)
- `notified`: count of entries that transitioned to `notify_status: "sent"` this cycle (new + drained from pending)
- `pending`: count of entries with `crm_status: "pending"` or `notify_status: "pending"` at cycle end
- `errors`: list of canonical token strings (see table above); empty list means a clean cycle

#### Step Invocation Interface

The orchestrator calls each step as a **direct Python function import** within the same process — not as a subprocess. This keeps the zero-infrastructure constraint (no IPC, no serialization overhead) and allows the orchestrator to catch typed exceptions from each step.

| Step | Module | Function | Call type |
|------|--------|----------|-----------|
| 1 — Gmail Intake | `gmail_intake.server` | `check_new_deals_handler()` | `async` — must be run via `asyncio.run()` |
| 2 — CRM Logger | `crm_logger.server` | `sync_deals_to_crm()` | synchronous |
| 3 — Discord Notifier | `discord_notifier.server` | `sync_notifications()` | synchronous |

**Return values on success** (each step returns a `dict`):

| Step | Return dict keys | Notes |
|------|-----------------|-------|
| 1 | `status`, `deals_extracted` (list), `processed_count` (int), `skipped_count` (int), `error_details` (str or null) | `status == "ok"` on success; `error_details` is a human-readable string describing the first error encountered, or `null` if none |
| 2 | `status`, `crm_logged` (int), `crm_pending` (int), `skipped` (int), `suspended` (bool), `error_details` (str or null) | `status == "ok"` on success; `error_details` is a human-readable string or `null`; see `suspended` semantics below |
| 3 | `status`, `discord_notified` (int), `notify_pending` (int), `skipped` (int), `error_details` (str or null) | `status == "ok"` on success; `error_details` is a human-readable string or `null` |

**Step 2 `suspended` field semantics**: `suspended: true` means step 2's internal HubSpot circuit breaker has tripped — 3 or more consecutive cycles have received HTTP 401 from HubSpot, so the step made **no HubSpot API calls** this cycle and all deal entries remain in their current state (unchanged). When `suspended: true`, the return dict carries: `crm_logged: 0`, `crm_pending: 0`, `skipped: 0` (zero because no entries were attempted). When the orchestrator reads `suspended: true`:

1. Log a WARN entry: "HubSpot CRM suspended — circuit breaker active; no deals logged this cycle."
2. **Proceed to step 3 normally** — Discord notifications are independent of HubSpot and any `notify_status: "pending"` entries can still be drained.
3. Include `"suspended": true` in the cycle summary log entry's `errors` list (e.g., `"errors": ["crm_suspended"]`).
4. Do NOT treat `suspended: true` as a cycle-aborting failure — the orchestrator process remains alive and step 3 runs.

The circuit breaker resets automatically once the operator rotates the HubSpot token and `consecutive_401_cycles` drops below the threshold; no orchestrator-level configuration is needed.

**Failure signaling — per-item vs cycle-aborting**:

- **Per-item failure** (recoverable, FR-006/FR-007): Steps 2 and 3 write `crm_status: "pending"` or `notify_status: "pending"` directly to the state store for the affected entry, then return normally with the failure count reflected in `crm_pending` / `notify_pending`. The orchestrator reads these counts from the return dict to populate the cycle summary.
- **Cycle-aborting failure — Gemini quota** (FR-005): Step 1 raises `gmail_intake.models.RateLimitExhaustedError`. The orchestrator catches this exception, logs it at ERROR level, releases the lock, and exits the cycle.
- **Cycle-aborting failure — Gmail OAuth** (FR-014): Step 1 raises `google.auth.exceptions.RefreshError` when the OAuth token has expired and the automatic refresh fails. The orchestrator catches this specific exception class, logs at ERROR level, releases the lock, and exits the cycle. The orchestrator process remains alive for the next scheduled cycle.
- **Cycle-aborting failure — unhandled** (FR-008): Any other uncaught exception propagating out of any step is caught at the orchestrator's top-level `try/finally` boundary, logged at ERROR level with full traceback, lock released, process continues running.

**Failure classification — transient vs permanent** (applies to steps 2 and 3):

| Class | Condition | Behaviour |
|-------|-----------|-----------|
| **Transient** | HTTP 429, 500, 502, 503, 504 | Set `crm_status: "pending"` or `notify_status: "pending"`; retry next cycle |
| **Permanent** | HTTP 400, 401, 403, 404 | Do NOT set `"pending"`; log at ERROR level; set `crm_status: "failed"` or `notify_status: "failed"`; never retry automatically |
| **Network error** | No HTTP response received (`ConnectionError`, `Timeout`, `ReadTimeout`, `SSLError`) | Treat as transient: set `crm_status: "pending"` or `notify_status: "pending"`; retry next cycle. If at least one network-level error occurred in the cycle, add the `"network_error"` token to the cycle summary `errors` list. |

Entries with `"failed"` status require operator inspection and manual re-trigger; they do not loop indefinitely.

A `"pending"` entry that remains unresolved for more than `MAX_PENDING_RETRIES` consecutive cycles is promoted to `"failed"` and logged at WARN level to prevent infinite retry accumulation.

#### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `POLL_INTERVAL_MINUTES` | `15` | Minutes between scheduled cycle triggers |
| `LOCK_TIMEOUT_MINUTES` | `30` | Minutes after which a cycle lock is considered stale |
| `LOG_MAX_BYTES` | `10485760` (10 MB) | Maximum log file size before rotation |
| `LOG_BACKUP_COUNT` | `3` | Number of rotated backup log files to keep |
| `MAX_PENDING_RETRIES` | `10` | Max cycles a `"pending"` entry is retried before being promoted to `"failed"` |
| `STATE_STORE_PATH` | (required) | Absolute path to `processed_ids.json` |

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new deal email arriving in the inbox is detected, CRM-logged, and Discord-notified within a single polling interval (`POLL_INTERVAL_MINUTES`, default ≤ 15 minutes) with zero manual tool invocation.
- **SC-002**: When Gemini quota is exhausted mid-cycle, the orchestrator exits that cycle cleanly within 10 seconds of detecting the quota error, with no stale `.pipeline.lock` and no corrupt `messages` entry remaining.
- **SC-003**: A second concurrent cycle trigger while a cycle is in progress is rejected 100% of the time; the in-progress cycle always completes without interference.
- **SC-004**: When a stale lock (older than `LOCK_TIMEOUT_MINUTES`) is detected, the next cycle clears it and proceeds within its normal startup sequence, with a WARN log entry written and no operator intervention.
- **SC-005**: Every completed cycle produces exactly one INFO-level JSON summary line with all six required fields (`ts`, `emails_processed`, `crm_logged`, `notified`, `pending`, `errors`).
- **SC-006**: Running the full pipeline 10 consecutive times against a static, fully-processed `processed_ids.json` produces zero new HubSpot deals and zero new Discord notifications across all 10 runs.
- **SC-007**: The orchestrator survives a machine reboot and resumes scheduled cycles automatically, confirmed by the presence of cycle log entries after reboot with no operator login required.
- **SC-008**: When the Gmail OAuth token fails to refresh, the cycle aborts with an ERROR log entry; `.pipeline.lock` is absent after the abort; `processed_ids.json` is byte-for-byte identical to its pre-cycle state.
- **SC-009**: When `processed_ids.json` is missing at cycle start, the cycle aborts with an ERROR log entry; the file is not created, truncated, or modified.
- **SC-010**: When the orchestrator starts with `STATE_STORE_PATH` absent or empty, it exits with a non-zero exit code and an error message before creating any lock file or running any cycle.
- **SC-011**: When the state-store directory blocks lock-file creation (permission denied), the cycle is skipped with an ERROR log entry; the orchestrator process remains running for the next scheduled cycle.
- **SC-012**: When a HubSpot or Discord write fails with an HTTP 4xx permanent error code, the affected entry's status field is set to `"failed"` (not `"pending"`) and never appears in a future automatic drain pass.
- **SC-013**: When an entry has been in `"pending"` status for `MAX_PENDING_RETRIES` drain-eligible cycles, it is promoted to `"failed"` with a WARN log entry containing its `gmail_message_id`, and subsequent drain passes skip it.
- **SC-014**: When step 2 returns `suspended: true`, step 3 still runs in that same cycle, a WARN log entry is written, and the cycle summary includes `"crm_suspended"` in its `errors` list.
- **SC-015**: When `POLL_INTERVAL_MINUTES` is set to a non-numeric value at startup, the orchestrator exits with a non-zero code and a message identifying the variable and valid range — no lock file is created and no cycle runs.
- **SC-016**: When `.pipeline.lock` contains non-ISO-8601 content, the next cycle treats it as stale: a WARN log entry is written, the file is deleted, and the cycle proceeds; no human intervention is required.
- **SC-017**: When the Gemini quota is exhausted after 2 emails have been classified in a cycle, both classified emails reach `crm_status: "logged"` and `notify_status: "sent"` within that same cycle — they are not deferred to the next cycle's drain pass.

---

## Constitution Check Gates *(explicit alignment)*

This spec has been evaluated against all 6 Constitution Check Gates:

| Gate | Question | Answer | Verdict |
|------|----------|--------|---------|
| I — Zero Cost | Does this introduce any paid dependency? | No. FR-002 mandates a zero-cost mechanism (cron, systemd timer, or native sleep-loop). FR-011 mandates local log rotation; no external paid logging service. SC-005's acceptance scenario (US4-5) confirms no paid logging reference in any log entry. | PASS |
| II — Gmail-Only Intake | Does this add a non-Gmail intake source? | No. Orchestration wires the existing Gmail intake; no new intake source is added. | PASS |
| III — Headless Operation | Does this require a runtime browser login? | No. FR-013 mandates automatic restart on reboot. FR-014 handles token refresh failure (aborts cycle, no browser prompt). The scheduler runs as a system service; all auth is token-based and pre-configured. | PASS |
| IV — State-Driven Idempotency | Does this risk duplicate CRM entries or duplicate alerts? | No. FR-012 mandates zero new deals/alerts on a fully-processed inbox. FR-003 (lock) eliminates the concurrent-cycle duplication vector. `crm_status` and `notify_status` fields on each entry provide per-step idempotency guards for the drain path (FR-006, FR-007). | PASS |
| V — Modular Notification | Does this modify core pipeline files to add a notification target? | No. This spec adds no new notifier. Orchestration calls the existing notifier interface unchanged. | PASS |
| VI — Graceful Degradation — complete failure-mode table | Does this allow any failure to crash the agent or corrupt state? | No. Full failure-mode coverage: (a) Gemini 429 quota exhaustion: FR-005 — log + clean exit, lock released; (b) HubSpot transient failure: FR-006 — `crm_status: "pending"`, cycle continues; (c) Discord transient failure: FR-007 — `notify_status: "pending"`, cycle continues; (d) Unhandled exception: FR-008 — caught at boundary, lock released, process stays alive; (e) Gmail OAuth refresh failure: FR-014 — log + clean abort, state store untouched; (f) Corrupt/missing state store: FR-015 — log + clean abort, file not modified; (g) SIGKILL mid-cycle: pending entries in state store are drained by next cycle's normal pass (FR-006/FR-007) — no manual recovery needed. | PASS |

---

## Assumptions

- Steps 1, 2, and 3 (gmail-intake, crm-logger, discord-notifier) remain unchanged in their internal logic; this spec only wires them together and adds a scheduler.
- The polling interval (default 15 minutes) is configurable via `POLL_INTERVAL_MINUTES`.
- Gemini billing is explicitly out of scope; the daily free-tier quota is a known constraint documented here for operator awareness, not resolved by this spec.
- The state store remains file-based JSON at `STATE_STORE_PATH`; no database migration is required.
- Log rotation uses `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT`; the mechanism is a system-native rotating file handler (available at zero cost on the operator's machine).
- "Machine reboot" means the operator's Linux/WSL machine; systemd is the canonical service manager for headless restart.
- The state store directory (containing `processed_ids.json`) is also the directory for the `.pipeline.lock` file.
- Gemini 429 back-off retries (up to 3, with 10 s / 30 s / 60 s delays) are handled inside the existing `classifier.py` (`RateLimitExhaustedError`). The orchestrator treats a `RateLimitExhaustedError` propagated from step 1 as the daily-quota exhaustion signal for FR-005.
- **FR-019 counter definition**: The `MAX_PENDING_RETRIES` counter for a `"pending"` entry counts only *drain-eligible cycles* — cycles where step 2 or step 3 **actually attempted** the entry. Specifically:
  - Cycles that abort before reaching step 2 (Gemini quota, Gmail OAuth failure, missing state store, lock creation failure) do **not** increment the counter — the entry was never attempted.
  - Cycles where step 2 returns `suspended: true` do **not** increment the counter for any `crm_status: "pending"` entry — step 2 made zero HubSpot API calls and no attempt was made against those entries. A HubSpot circuit-break must not count against an entry's retry budget.
  - Only cycles where step 2 actively attempted the entry (received an HTTP response, whether success or transient failure) increment the counter.
  - The same logic applies to `notify_status: "pending"` entries and step 3: only cycles where step 3 actually attempted the Discord call increment the counter.
- **FR-014 vs Constitution Principle VI ("pause polling")**: Principle VI's intent is that a transient authentication failure must not crash the process. FR-014 satisfies this by aborting the cycle cleanly and retrying on the next scheduled cycle, which achieves the same protective outcome. "Pause polling" in the constitution refers to not continuing to hammer a failing service — FR-014 does this by aborting step 1 immediately rather than retrying the OAuth call within the same cycle. This interpretation is intentional for this spec: a full scheduling pause (suppressing future cycles) is not warranted for a recoverable token expiry that may self-heal on the next cycle.

---

## Out of Scope

- Any change to the internal classification, CRM-write, or notification logic of steps 1–3.
- Enabling Gemini billing (a business decision outside this technical spec).
- New notification channels (Slack, Email, SMS) — extensibility was delivered in Step 3.
- A UI or dashboard for monitoring — log files are the observability surface for this MVP.
- Cloud-hosted deployment — systemd on the operator's local machine is the target.
- HubSpot rate-limit back-off within the CRM-write step — that is internal to step 2 and outside this spec's boundary.
