# Tasks: Pipeline Orchestration, Error Handling & End-to-End Wiring

**Input**: Design documents from `specs/004-pipeline-orchestration/`
**Prerequisites**: spec.md ✅ plan.md ✅ research.md ✅ quickstart.md ✅
**Branch**: `004-pipeline-orchestration`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story this task belongs to (US1–US5)

---

## Phase 1: Setup

**Purpose**: Create the new package directory; no code from steps 1–3 is modified.

- [ ] T001 Create `src/pipeline_orchestrator/__init__.py` with package docstring
- [ ] T002 Create `tests/unit/test_orchestrator_config.py`, `tests/unit/test_orchestrator_lock.py`, `tests/unit/test_cycle_logger.py`, `tests/unit/test_orchestrator_runner.py`, `tests/integration/test_full_pipeline.py` as empty placeholder files so pytest discovers them

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The three core modules that every user story depends on. All three can be implemented in parallel — they share no cross-dependencies.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Implement `PipelineConfig` dataclass and `load_config()` in `src/pipeline_orchestrator/config.py` — reads `STATE_STORE_PATH` (required), `POLL_INTERVAL_MINUTES` (int ≥ 1, default 15), `LOCK_TIMEOUT_MINUTES` (int ≥ 1, default 30), `PIPELINE_LOG_PATH` (default `<state_store_dir>/pipeline.log`), `LOG_MAX_BYTES` (int ≥ 1, default 10485760), `LOG_BACKUP_COUNT` (int ≥ 0, default 3), `MAX_PENDING_RETRIES` (int ≥ 1, default 10), `SCHEDULER_MODE` ("loop"|"systemd", default "loop"); exits with code 1 and a clear message for any missing or out-of-range value (FR-016, FR-020)
- [ ] T004 [P] Implement `CycleLogger` class and `emit_cycle_summary()` in `src/pipeline_orchestrator/cycle_logger.py` — sets up `logging.handlers.RotatingFileHandler` with `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT`; `emit_cycle_summary(ts, emails_processed, crm_logged, notified, pending, errors)` writes a single INFO-level JSON line with exactly those six fields (FR-009, FR-011)
- [ ] T005 [P] Implement `CycleLock` context manager and `CycleLockActiveError` in `src/pipeline_orchestrator/lock.py` — on `__enter__`: read `<state_store_dir>/.pipeline.lock` if present; if content unparseable as UTC ISO-8601 timestamp, treat as stale (WARN log, delete, proceed); if parseable and age < `LOCK_TIMEOUT_MINUTES`, raise `CycleLockActiveError`; if stale (age ≥ `LOCK_TIMEOUT_MINUTES`), log WARN with creation timestamp, delete, proceed; write new lock file with `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`; on `__exit__`: delete lock file in `finally`; if deletion fails, log WARN, do not raise (FR-003, FR-004, FR-017, FR-021)

**Checkpoint**: config.py, cycle_logger.py, lock.py complete — user story phases can now begin.

---

## Phase 3: US1 — Fully Automated Deal Pipeline (P1) 🎯 MVP

**Goal**: Deliver a working end-to-end orchestrated pipeline that runs on a schedule without manual intervention.

**Independent Test**: Set `SCHEDULER_MODE=systemd`, run `python -m pipeline_orchestrator` with a clean state store, confirm a JSON cycle summary line is written to `PIPELINE_LOG_PATH` with all six fields and no errors.

### Tests for User Story 1

- [ ] T006 [P] [US1] Write unit tests for `config.py` in `tests/unit/test_orchestrator_config.py` — (a) valid minimal config loads without error; (b) missing `STATE_STORE_PATH` → `SystemExit(1)` with message; (c) `POLL_INTERVAL_MINUTES=0` → `SystemExit(1)`; (d) `POLL_INTERVAL_MINUTES=abc` → `SystemExit(1)`; (e) all defaults are applied when optional vars absent
- [ ] T007 [P] [US1] Write unit tests for `lock.py` in `tests/unit/test_orchestrator_lock.py` — (a) fresh lock: file created at `__enter__`, deleted at `__exit__`; (b) existing non-stale lock: `CycleLockActiveError` raised, existing file untouched; (c) stale lock (timestamp > `LOCK_TIMEOUT_MINUTES`): WARN logged, file deleted, new lock created; (d) malformed lock content: WARN logged, treated as stale; (e) `__exit__` on exception: lock file still deleted (finally semantics)
- [ ] T008 [P] [US1] Write unit tests for `cycle_logger.py` in `tests/unit/test_cycle_logger.py` — (a) `emit_cycle_summary` writes valid JSON with all six fields (`ts`, `emails_processed`, `crm_logged`, `notified`, `pending`, `errors`); (b) `errors` list correctly includes/excludes tokens; (c) `RotatingFileHandler` is configured with `maxBytes` and `backupCount` from config

### Implementation for User Story 1

- [ ] T009 [US1] Implement `run_cycle(config, logger)` in `src/pipeline_orchestrator/runner.py` — acquire `CycleLock`; in `try`: call `asyncio.run(check_new_deals_handler())` (catch `RateLimitExhaustedError` → append `"quota_exhausted"` to errors, continue to step 2; catch `google.auth.exceptions.RefreshError` → append `"gmail_oauth_failed"`, goto finally); call `sync_deals_to_crm()` (catch unhandled exception → append `"unhandled_exception"`, continue to step 3; if `result["suspended"]` → append `"crm_suspended"`); call `sync_notifications()` (catch unhandled exception → append `"unhandled_exception"`); in `finally`: release lock, call `emit_cycle_summary` with aggregated counts from return dicts and errors list (FR-001, FR-005, FR-006, FR-007, FR-008, FR-022)
- [ ] T010 [US1] Implement `run_loop(config, logger)` in `src/pipeline_orchestrator/scheduler.py` — `while not _shutdown_flag`: call `run_cycle(config, logger)`, catch `CycleLockActiveError` (log WARN `"concurrent cycle detected — skipping"`), then `time.sleep(config.poll_interval_minutes * 60)`; export `_shutdown_flag` as a module-level `threading.Event` so `__main__.py` can set it from the SIGTERM handler (FR-001, FR-002)
- [ ] T011 [US1] Implement `main()` and SIGTERM handler in `src/pipeline_orchestrator/__main__.py` — (a) call `load_config()` (exits on validation failure, FR-016, FR-020); (b) call `logging.basicConfig` + instantiate `CycleLogger(config)`; (c) install SIGTERM handler: `signal.signal(signal.SIGTERM, _sigterm_handler)` where handler sets `scheduler._shutdown_flag` so the current cycle completes before the process exits (FR-023); (d) if `config.scheduler_mode == "systemd"`: call `run_cycle(config, logger)` then `sys.exit(0)`; else: call `run_loop(config, logger)` (FR-013)
- [ ] T012 [US1] Write unit tests for `runner.py` in `tests/unit/test_orchestrator_runner.py` — mock `check_new_deals_handler`, `sync_deals_to_crm`, `sync_notifications` and `CycleLock`; (a) clean cycle with no new deals: all steps called, summary emitted with zeros; (b) `RateLimitExhaustedError` from step 1: `"quota_exhausted"` in errors, steps 2 and 3 still called (FR-022); (c) `RefreshError` from step 1: `"gmail_oauth_failed"` in errors, steps 2 and 3 NOT called; (d) unhandled exception from step 2: `"unhandled_exception"` in errors, step 3 still called; (e) lock always released even on exception (finally block fires)

**Checkpoint**: `python -m pipeline_orchestrator` runs a single cycle in systemd mode and exits 0, writing a valid cycle summary log line.

---

## Phase 4: US2 — Concurrent Cycle Prevention (P2)

**Goal**: Guarantee that a second cycle trigger never runs while a cycle is already in progress.

**Independent Test**: Create a fresh `.pipeline.lock` file, call `run_cycle()`, confirm `CycleLockActiveError` is raised and no step function is called.

### Tests for User Story 2

- [ ] T013 [US2] Write integration tests for lock behaviour in `tests/integration/test_full_pipeline.py` — (a) SC-003: pre-create a fresh `.pipeline.lock` (timestamp = now), call `run_cycle()`, confirm `CycleLockActiveError` raised and mock steps not called, confirm lock file unchanged; (b) SC-004: pre-create a stale `.pipeline.lock` (timestamp = 35 minutes ago with `LOCK_TIMEOUT_MINUTES=30`), call `run_cycle()`, confirm WARN log written, old lock cleared, cycle proceeds; (c) SC-016: pre-create `.pipeline.lock` with content "NOT_A_TIMESTAMP", call `run_cycle()`, confirm malformed-lock WARN logged, lock cleared, cycle proceeds normally

**Checkpoint**: All three lock-behaviour scenarios verified by integration tests.

---

## Phase 5: US3 — Quota and Transient Error Resilience (P3)

**Goal**: Every named external failure mode exits cleanly with no stale lock and no corrupt state store entry.

**Independent Test**: Inject a mock `RateLimitExhaustedError` from step 1 after one entry is classified; confirm steps 2 and 3 still run for that entry and the cycle exits cleanly (no `.pipeline.lock` remaining).

### Implementation for User Story 3

- [ ] T014 [P] [US3] Extend `runner.py` to track and enforce `MAX_PENDING_RETRIES` in `src/pipeline_orchestrator/runner.py` — after `sync_deals_to_crm()` returns, open the state store (with portalocker), read each `deal_extracted` entry that has `crm_status: "pending"` (where set by step 2 or on previous cycle), increment its `crm_retry_count` field; if `crm_retry_count >= MAX_PENDING_RETRIES`, promote to `crm_status: "failed"` and append `"pending_promoted_to_failed"` to errors; mirror logic for `notify_status` / `notify_retry_count` after `sync_notifications()` (FR-019)
- [ ] T015 [P] [US3] Extend `runner.py` to write `crm_status` and `notify_status` fields into the state store in `src/pipeline_orchestrator/runner.py` — after step 2 completes, open the state store (with portalocker), for each `deal_extracted` entry: if now `status == "crm-logged"` → write `crm_status: "logged"` and `crm_retry_count: 0`; else if step 2 attempted it (i.e., `crm_logged + crm_pending > 0`) → write `crm_status: "pending"`, increment `crm_retry_count`; mirror for `notify_status` / `notify_retry_count` after step 3 (FR-006, FR-007, FR-018)

### Tests for User Story 3

- [ ] T016 [US3] Write integration tests for error resilience in `tests/integration/test_full_pipeline.py` — (a) SC-002: mock `RateLimitExhaustedError` from step 1 with 2 already-classified entries; confirm `.pipeline.lock` absent after cycle, no corrupt state store entry, `"quota_exhausted"` in cycle summary errors; (b) SC-017: same setup; confirm `crm_logged == 2` in cycle summary (both classified entries drain through steps 2+3 in same cycle); (c) SC-012: mock step 2 returning `crm_pending: 1` for an entry; confirm `crm_status: "pending"` written and entry present in drain pass next cycle; (d) SC-014: mock step 2 returning `suspended: True`; confirm step 3 still called, `"crm_suspended"` in errors

**Checkpoint**: All four error-resilience scenarios pass.

---

## Phase 6: US4 — Operational Log Visibility (P4)

**Goal**: Every cycle produces exactly one INFO-level JSON summary line with all six required fields.

**Independent Test**: Run a single cycle, read `PIPELINE_LOG_PATH`, confirm exactly one JSON line present containing all six fields with correct types.

### Tests for User Story 4

- [ ] T017 [US4] Write integration tests for log visibility in `tests/integration/test_full_pipeline.py` — (a) SC-005: run a clean cycle; parse `PIPELINE_LOG_PATH`; confirm exactly one INFO line, valid JSON, all six fields (`ts`, `emails_processed`, `crm_logged`, `notified`, `pending`, `errors`), `errors == []`; (b) SC-005 with error: inject mock exception from step 2; confirm `errors` list contains `"unhandled_exception"` token exactly once (dedup rule); (c) FR-011: set `LOG_MAX_BYTES=1024` and run 50 cycles; confirm log file does not exceed ~3× `LOG_MAX_BYTES` (rotation working)

**Checkpoint**: Cycle summary format verified programmatically.

---

## Phase 7: US5 — Startup Guard and Retry Limits (P5)

**Goal**: Orchestrator refuses to start with invalid config; permanent failures never loop indefinitely; SIGTERM exits cleanly with lock released.

**Independent Test**: Start orchestrator with `STATE_STORE_PATH` unset — confirm non-zero exit code and clear error message with no lock file created.

### Tests for User Story 5

- [ ] T018 [P] [US5] Write integration tests for startup guard in `tests/integration/test_full_pipeline.py` — (a) SC-010: unset `STATE_STORE_PATH`, call `load_config()`, confirm `SystemExit(1)` raised before any lock file created; (b) SC-015: set `POLL_INTERVAL_MINUTES=0`, call `load_config()`, confirm `SystemExit(1)` with message identifying variable and valid range; (c) SC-009: point `STATE_STORE_PATH` to non-existent path, call `run_cycle()`, confirm ERROR log written, cycle aborts cleanly, `.pipeline.lock` absent after abort, file not created
- [ ] T019 [P] [US5] Write integration tests for retry limits and SIGTERM in `tests/integration/test_full_pipeline.py` — (a) SC-013: inject an entry with `crm_status: "pending"` and `crm_retry_count == MAX_PENDING_RETRIES - 1`; run one cycle where step 2 still fails; confirm `crm_status` promoted to `"failed"`, `"pending_promoted_to_failed"` in errors, entry absent from next drain pass; (b) FR-023: start `run_cycle()` in a thread, send `SIGTERM` mid-cycle; join thread; confirm `.pipeline.lock` absent after thread exits and cycle summary was emitted

**Checkpoint**: All startup-guard and retry-limit scenarios pass.

---

## Phase 8: Deployment (systemd)

**Purpose**: Provide ready-to-use systemd unit files and installation guide. No Python changes.

- [ ] T020 [P] Create `deploy/openclaw.service` — `Type=oneshot`, `ExecStart=.venv/bin/python -m pipeline_orchestrator`, `EnvironmentFile=.env`, `Environment=SCHEDULER_MODE=systemd` (see plan.md for full unit content)
- [ ] T021 [P] Create `deploy/openclaw.timer` — `OnBootSec=1min`, `OnUnitActiveSec=15min`, `AccuracySec=30s`, `WantedBy=timers.target` (see plan.md for full unit content)
- [ ] T022 Create `deploy/README.md` — systemd installation steps (`daemon-reload`, `enable --now openclaw.timer`, `status`), log inspection (`journalctl -u openclaw.service`), cron fallback instructions for operators without systemd, WSL2 systemd enablement check (`/etc/wsl.conf` `[boot] systemd=true`)

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation that spans all user stories.

- [ ] T023 Write integration test for full end-to-end idempotency in `tests/integration/test_full_pipeline.py` — SC-006: load a fully-processed state store (all entries `crm_status: "logged"`, `notify_status: "sent"`); run `run_cycle()` 3 times; confirm `crm_logged == 0` and `notified == 0` in all three cycle summaries and state store is byte-for-byte identical after each run
- [ ] T024 Run full pytest suite (`pytest tests/ -v`) and confirm all pre-existing tests (001/002/003 features) still pass alongside all new orchestrator tests
- [ ] T025 Manually verify quickstart.md scenarios 1–6 against the implemented code and mark each scenario as confirmed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories; T003, T004, T005 are independent and can run in parallel
- **US1 (Phase 3)**: Depends on Phase 2 — T006, T007, T008 (tests) can run in parallel; T009, T010, T011, T012 are sequential (runner before scheduler before __main__ before runner tests)
- **US2 (Phase 4)**: Depends on Phase 3 completion (needs CycleLock + runner)
- **US3 (Phase 5)**: Depends on Phase 3; T014 and T015 can run in parallel (different aspects of runner.py)
- **US4 (Phase 6)**: Depends on Phase 3 (needs cycle_logger + runner)
- **US5 (Phase 7)**: Depends on Phase 3 (needs config + runner); T018 and T019 can run in parallel
- **Deployment (Phase 8)**: Independent of Phases 3–7 — can run any time after Phase 1; T020, T021 in parallel
- **Polish (Phase 9)**: Depends on all Phases 3–8

### User Story Dependencies

- **US1 (P1)**: Only depends on Foundational — no other story dependencies
- **US2 (P2)**: Depends on US1 (integration tests use runner.py)
- **US3 (P3)**: Depends on US1 (extends runner.py)
- **US4 (P4)**: Depends on US1 (integration tests use runner.py + cycle_logger)
- **US5 (P5)**: Depends on US1 (uses runner.py + config.py)

### Parallel Opportunities

```
# Phase 2 — all three modules in parallel:
T003 config.py  |  T004 cycle_logger.py  |  T005 lock.py

# Phase 3 — unit tests in parallel with each other:
T006 test_config  |  T007 test_lock  |  T008 test_cycle_logger

# Phase 5 — runner.py extensions:
T014 retry-count tracking  |  T015 crm_status/notify_status writes

# Phase 7 — integration test groups:
T018 startup guard  |  T019 retry limits + SIGTERM

# Phase 8 — deployment files:
T020 openclaw.service  |  T021 openclaw.timer
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundational: config.py, cycle_logger.py, lock.py)
3. Complete Phase 3 (US1: runner.py + scheduler.py + __main__.py + unit tests)
4. **STOP and VALIDATE**: Run `python -m pipeline_orchestrator` in systemd mode, confirm cycle summary JSON written, all unit tests pass
5. MVP is usable: operator can run the pipeline manually or via cron

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → One-shot and loop mode working → **MVP**
3. US2 → Concurrent-cycle safety confirmed
4. US3 → All failure modes handled
5. US4 → Log observability verified
6. US5 → Startup guard + retry limits + SIGTERM hardened
7. Deployment files → Production-ready systemd install

---

## Notes

- Steps 1–3 (`gmail_intake`, `crm_logger`, `discord_notifier`) are NOT modified in any task
- T009 (runner.py) is the single most complex task — it wires all three steps and handles all exception paths; allow extra time
- T014/T015 (retry counting + crm_status writes) require acquiring the portalocker lock on the state store before any read-modify-write — use the existing `portalocker` pattern from step 1
- `asyncio.run()` for step 1: do not use `loop.run_until_complete()` (deprecated); `asyncio.run()` creates a new event loop per call which is correct for a one-shot orchestrator
- SIGTERM handler (T011) must set a `threading.Event`, not a bare bool, so that `run_loop()` wakes from `time.sleep()` immediately rather than waiting for the sleep to expire
