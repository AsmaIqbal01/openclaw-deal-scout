---
id: "0006"
title: Email Scheduling Full Implementation
stage: green
date: 2026-07-26
surface: agent
model: claude-sonnet-4-6
feature: 007-email-scheduling
branch: 007-email-scheduling
user: AsmaIqbal01
command: /sp.implement
labels: ["implementation","email-scheduler","pipeline","gmail-api","dashboard","tests"]
links:
  spec: specs/007-email-scheduling/spec.md
  ticket: null
  adr: history/adr/ADR-0008-gmail-api-send.md, history/adr/ADR-0009-email-dispatch-threading-model.md
  pr: null
files:
  - src/email_scheduler/__init__.py
  - src/email_scheduler/config.py
  - src/email_scheduler/models.py
  - src/email_scheduler/queue_store.py
  - src/email_scheduler/audit_logger.py
  - src/email_scheduler/template.py
  - src/email_scheduler/auth.py
  - src/email_scheduler/scheduler.py
  - src/openclaw_gateway/routes/email_api.py
  - src/openclaw_gateway/server.py
  - src/openclaw_gateway/static/dashboard.html
  - src/pipeline_orchestrator/runner.py
  - src/pipeline_orchestrator/cycle_logger.py
  - tests/unit/test_email_scheduler_config.py
  - tests/unit/test_email_scheduler_template.py
  - tests/unit/test_email_scheduler_queue_store.py
  - tests/unit/test_email_scheduler_scheduler.py
  - tests/unit/test_email_scheduler_audit.py
  - tests/unit/test_email_scheduler_api.py
  - tests/integration/test_email_scheduling_e2e.py
  - specs/007-email-scheduling/tasks.md
tests:
  - tests/unit/test_email_scheduler_config.py (16 tests — config validation, defaults, overrides)
  - tests/unit/test_email_scheduler_template.py (14 tests — subject derivation, body substitution, custom templates)
  - tests/unit/test_email_scheduler_queue_store.py (36 tests — create/dedup/load/approve/cancel/mark_sent/mark_retry/thread-safety)
  - tests/unit/test_email_scheduler_scheduler.py (31 tests — schedule_for_deal paths, business-hours, dispatch_pending)
  - tests/unit/test_email_scheduler_audit.py (14 tests — write/get_events/load_existing/startup-recovery)
  - tests/unit/test_email_scheduler_api.py (16 tests — approve/cancel/list-emails/list-events REST handlers)
  - tests/integration/test_email_scheduling_e2e.py (8 tests — full schedule→approve→dispatch cycle, retry flow, recovery)
---

## Prompt

/sp.implement

## Response snapshot

Full implementation of `007-email-scheduling` feature across 34 tasks (T001–T033):

**Core package** (`src/email_scheduler/`): `config.py` (EmailSchedulerConfig + load_email_config), `models.py` (ScheduledEmail, EmailEvent, EmailStatus, EventType, AuthError), `queue_store.py` (EmailQueueStore with atomic writes, threading.Lock, approve/cancel/mark_sent/mark_retry, startup recovery via _repair_from_audit), `audit_logger.py` (AuditLogger JSONL append, in-memory event list, thread-safe), `template.py` (render_email with subject/body fallback rules), `auth.py` (build_send_service with gmail.send scope), `scheduler.py` (schedule_for_deal, dispatch_pending, is_business_hours, next_business_window — all MUST NOT raise).

**Pipeline integration**: runner.py step 4a (schedule per discord-notified deal) + step 4b (dispatch approved emails); cycle_logger.py extended with optional email fields.

**Gateway REST API**: 4 new routes registered in server.py — GET /api/emails, POST /api/emails/{id}/approve, POST /api/emails/{id}/cancel, GET /api/email-events.

**Dashboard**: email queue panel (approve/cancel buttons) + collapsible audit history panel added to dashboard.html.

**Critical fix**: SystemExit from load_email_config() (sys.exit(1) on missing env vars) now caught in runner.py steps 4a/4b and inside scheduler.py functions to honour the MUST NOT raise contract in test environments without email config.

**Test suite**: 489 passed, 9 skipped (0 failures). Pre-existing 363 tests + 126 new email_scheduler tests all green.

## Outcome

- ✅ Impact: Complete 007-email-scheduling feature implemented — auto-scheduling, operator approval gate, UK business-hours dispatch, Gmail API send, full audit trail, startup recovery
- 🧪 Tests: 489 passed, 9 skipped, 0 failed (pytest --tb=short -q)
- 📁 Files: 13 source files created/modified, 7 test files created (126 new test cases)
- 🔁 Next prompts: T034 manual quickstart.md validation with live Gmail credentials (requires token.json with gmail.send scope); /git-checkpoint to commit the feature
- 🧠 Reflection: The SystemExit propagation from load_email_config() was the key regression — caught by adding except SystemExit in both runner.py step handlers and within scheduler.py MUST NOT raise functions. Singleton reset fixture (autouse) in scheduler tests was essential to avoid cross-test state pollution.

## Evaluation notes (flywheel)

- Failure modes observed: SystemExit (BaseException, not Exception) from sys.exit(1) in load_email_config() propagated through pipeline runner test suite; patch targets for lazy imports inside function bodies required patching at source module not call site
- Graders run and results (PASS/FAIL): Full pytest suite — PASS (489/489 non-skipped)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Refactor load_email_config() to raise EmailSchedulerConfigError instead of sys.exit(1) to make the MUST NOT raise guarantee easier to test without sys.exit mocking
