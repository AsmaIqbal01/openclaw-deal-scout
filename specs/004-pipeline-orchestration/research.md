# Research: Pipeline Orchestration, Error Handling & End-to-End Wiring

**Branch**: `004-pipeline-orchestration` | **Date**: 2026-07-22
**Feeds into**: plan.md Phase 1

---

## Decision 1 — Scheduler Mechanism

**Decision**: Dual-mode deployment — systemd timer as canonical production mode; native sleep-loop (`time.sleep`) as dev/test mode.

**Rationale**:
- systemd timer provides lifecycle management (restart on reboot, `journalctl` log integration, dependency ordering) that aligns with Constitution Principle III (headless) and FR-013 (auto-start on reboot).
- A native sleep-loop mode (`while True: run_cycle(); sleep(N*60)`) makes local development and testing possible without a systemd installation, and is a valid alternative per FR-002.
- Cron is not chosen as primary because it has no native restart-on-reboot without `@reboot`, no built-in concurrency guard (that is handled at the application layer by FR-003), and no process supervision.

**Mode selection**: Controlled by `SCHEDULER_MODE=systemd|loop` env var. Default: `loop` (safest for first-run; operator switches to `systemd` when service files are installed).

**Alternatives considered**:
- APScheduler (Python): paid-nothing, but adds a dependency and is overkill for a single interval job.
- `cron`: free and universal, but restart-on-reboot requires `@reboot` entry which is less reliable than systemd WantedBy=multi-user.target.
- Celery: rejected, requires Redis or RabbitMQ (paid infrastructure, violates Principle I).

---

## Decision 2 — New Module Layout

**Decision**: New top-level package `src/pipeline_orchestrator/` alongside existing packages.

**Rationale**: Keeps steps 1-3 packages untouched (constitution requirement). The orchestrator is an independently testable coordination layer. Placing it in `src/` maintains consistency with the existing package structure and allows `python -m pipeline_orchestrator` as the entry point.

**Alternatives considered**:
- A single `src/orchestrator.py` script: simpler, but harder to unit-test individual concerns (lock management, config validation, cycle logging).
- Adding orchestration to `src/gmail_intake/server.py`: rejected — would violate the "no changes to step 1-3 internals" constraint from the spec.

---

## Decision 3 — Entry Point

**Decision**: `python -m pipeline_orchestrator` invokes `src/pipeline_orchestrator/__main__.py`, which:
1. Calls `load_config()` for startup validation (FR-016, FR-020)
2. If `SCHEDULER_MODE=loop`: enters the sleep-loop (`scheduler.py`)
3. If `SCHEDULER_MODE=systemd`: runs a single cycle (`runner.py`) and exits — the systemd timer re-invokes on each interval

**Rationale**: systemd timers work best with one-shot invocations (the timer is the scheduler, not the process). The sleep-loop mode is a convenience wrapper for dev/test. Both modes share the same `run_cycle()` core.

---

## Decision 4 — Log File Location

**Decision**: `PIPELINE_LOG_PATH` env var (new, added to plan env var table). Default: `<STATE_STORE_DIR>/pipeline.log`.

**Rationale**: Colocating the log with the state store keeps all operational files in one operator-visible directory. Rotation via Python's `RotatingFileHandler` (stdlib, zero cost) satisfies FR-011.

---

## Decision 5 — FR-022 Mid-batch Quota Abort Implementation

**Decision**: `run_cycle()` wraps `asyncio.run(check_new_deals_handler())` in a `try/except RateLimitExhaustedError` block. On catching the exception, it adds `"quota_exhausted"` to the errors list and **continues** to call `sync_deals_to_crm()` and `sync_notifications()` before exiting.

**Rationale**: Step 1 writes each classified entry to the state store before raising the error. Step 2 picks up any `deal_extracted` entries written before the abort — no special coordination needed between steps. This is "free" behaviour from the existing step 2 drain logic.

**Alternatives considered**:
- Skip steps 2+3 on quota error: simpler code, but leaves classified entries un-CRM-logged until the next cycle, violating the spirit of SC-017.

---

## Decision 6 — WSL2 Systemd Availability

**Finding**: Ubuntu 22.04 on WSL2 supports systemd when `/etc/wsl.conf` contains `[boot] systemd=true`. The operator's machine (Windows 10 Pro, WSL2 Ubuntu 22.04) satisfies this. The deploy/ directory will include `openclaw.service` and `openclaw.timer` files plus a `deploy/README.md` with installation steps.

**Alternatives considered**: Cron fallback documented in `deploy/README.md` for operators without systemd.

---

## Decision 7 — Pending Retry Counter Storage

**Decision**: The retry counter for `MAX_PENDING_RETRIES` is stored as a new field `crm_retry_count` (int, default 0) and `notify_retry_count` (int, default 0) on each entry in `processed_ids.json`, incremented by the orchestrator during each drain pass where the entry is attempted and still fails.

**Rationale**: Storing the counter in the state store is the only durable option — in-memory counters are lost on restart. A separate counter file would require additional locking.

**State store extension** (addition to spec schema):
```json
{
  "crm_status": "pending",
  "crm_retry_count": 3,
  "notify_status": "pending",
  "notify_retry_count": 1
}
```
