---
id: "030"
title: Pipeline Orchestration Tasks
stage: tasks
date: 2026-07-22
surface: agent
model: claude-sonnet-4-6
feature: pipeline-orchestration
branch: 004-pipeline-orchestration
user: AsmaIqbal000
command: /sp.tasks
labels: ["tasks","orchestration","pipeline","scheduling","error-handling","sigterm","systemd"]
links:
  spec: specs/004-pipeline-orchestration/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/004-pipeline-orchestration/tasks.md
tests:
  - tests/unit/test_orchestrator_config.py
  - tests/unit/test_orchestrator_lock.py
  - tests/unit/test_cycle_logger.py
  - tests/unit/test_orchestrator_runner.py
  - tests/integration/test_full_pipeline.py
---

## Prompt

/sp.tasks

(Feature context: 004-pipeline-orchestration — Orchestration, Error Handling & End-to-End Wiring. Spec.md has 23 FRs, 5 User Stories (US1–US5), plan.md defines src/pipeline_orchestrator/ package with config.py, lock.py, runner.py, scheduler.py, cycle_logger.py, __main__.py, deploy/ unit files, and tests/unit/ + tests/integration/.)

## Response snapshot

Generated `specs/004-pipeline-orchestration/tasks.md` with 25 tasks across 9 phases:

- **Phase 1 — Setup (T001–T002)**: Create package __init__.py and placeholder test files
- **Phase 2 — Foundational (T003–T005, parallel)**: config.py (PipelineConfig + load_config), cycle_logger.py (RotatingFileHandler + emit_cycle_summary), lock.py (CycleLock + CycleLockActiveError)
- **Phase 3 — US1 Fully Automated Pipeline (T006–T012)**: Unit tests for all 3 foundational modules + runner.py (run_cycle with full exception matrix) + scheduler.py (run_loop + _shutdown_flag Event) + __main__.py (SIGTERM handler, mode dispatch)
- **Phase 4 — US2 Concurrent Cycle Prevention (T013)**: Integration tests for fresh-lock rejection, stale-lock clearance, malformed-lock recovery
- **Phase 5 — US3 Error Resilience (T014–T016)**: runner.py extensions for crm_status/notify_status writes + retry-count tracking; integration tests for quota abort drain, circuit-breaker suspended, permanent failure
- **Phase 6 — US4 Log Visibility (T017)**: Integration tests for 6-field JSON format, dedup of error tokens, log rotation
- **Phase 7 — US5 Startup Guard + Retry Limits (T018–T019)**: Integration tests for missing STATE_STORE_PATH SystemExit, invalid env var ranges, MAX_PENDING_RETRIES promotion, SIGTERM mid-cycle lock release
- **Phase 8 — Deployment (T020–T022, parallel)**: openclaw.service, openclaw.timer, deploy/README.md
- **Phase 9 — Polish (T023–T025)**: End-to-end idempotency test (10 runs on fully-processed store), full pytest suite, quickstart.md scenario verification

Key design decisions recorded in tasks:
- T009 (runner.py) is the critical path task — all exception paths inline; RateLimitExhaustedError allows steps 2+3 to proceed (FR-022); RefreshError aborts after step 1
- T014/T015 can run in parallel (retry-count tracking vs crm_status field writes are independent aspects of runner.py)
- SIGTERM handler uses threading.Event for _shutdown_flag (not bare bool) so run_loop wakes immediately from time.sleep
- Steps 1–3 (gmail_intake, crm_logger, discord_notifier) are explicitly NOT modified in any task
- asyncio.run() mandated for step 1 call (not loop.run_until_complete — deprecated)
- Orchestrator reads state store before/after step 2 to infer crm_status, since steps 2/3 are unchanged

## Outcome

- ✅ Impact: Complete 25-task execution plan for the pipeline_orchestrator package, organized by user story and parallelism
- 🧪 Tests: 5 test files planned (4 unit, 1 integration) covering all 17 SCs from spec.md
- 📁 Files: specs/004-pipeline-orchestration/tasks.md created
- 🔁 Next prompts: /sp.implement
- 🧠 Reflection: The key design tension resolved in tasks: steps 1–3 are "unchanged" per plan.md constraint, but crm_status/notify_status must be written SOMEWHERE — tasks assign this to the orchestrator via a state-store read-after-step-2 pattern, avoiding modifying existing step functions while still satisfying FR-006/FR-007/FR-018

## Evaluation notes (flywheel)

- Failure modes observed: None (tasks generated from established spec + plan without ambiguity)
- Graders run and results (PASS/FAIL): none — tasks not scored by spec-scorer
- Prompt variant (if applicable): standard sp.tasks flow
- Next experiment: /sp.implement — T009 (runner.py) expected to be the hardest single task due to the full exception matrix
