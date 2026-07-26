---
id: "0005"
title: Email Scheduling Tasks 007
stage: tasks
date: 2026-07-26
surface: agent
model: claude-sonnet-4-6
feature: 007-email-scheduling
branch: 007-email-scheduling
user: AsmaIqbal01
command: /sp.tasks
labels: ["tasks","email-scheduler","007-email-scheduling","queue-store","audit-logger","gmail-api","business-hours","threading","dashboard"]
links:
  spec: specs/007-email-scheduling/spec.md
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - specs/007-email-scheduling/tasks.md
tests:
  - "null"
---

## Prompt

/sp.tasks

## Response snapshot

Generated `specs/007-email-scheduling/tasks.md` — 34 tasks across 7 phases, organized by user story priority.

Prerequisites confirmed via check-prerequisites.sh: FEATURE_DIR=/home/asmaiqbal01/openclaw-deal-scout/specs/007-email-scheduling, all design docs present (spec.md, plan.md, data-model.md, research.md, contracts/, quickstart.md).

Tasks organized by the 4 user stories from spec.md:

- Phase 1 (Setup) — 1 task: T001 — create email_scheduler package structure + pyproject.toml verification
- Phase 2 (Foundational, blocking all stories) — 4 tasks: T002 config.py, T003 models.py, T004 queue_store.py (create/list/dedup), T005 audit_logger.py
- Phase 3 (US1 P1: Auto-Schedule) — 8 tasks: T006 template.py, T007 schedule_for_deal(), T008 __init__.py exports, T009 runner.py step 4a, T010-T013 unit tests (config, template, queue_store, scheduler)
- Phase 4 (US2 P2: Approval Gate) — 6 tasks: T014 approve/cancel in queue_store, T015 email_api.py REST handlers, T016 server.py route registration, T017 dashboard email queue panel, T018-T019 unit tests
- Phase 5 (US3 P3: Smart Send-Time) — 7 tasks: T020 auth.py build_send_service, T021 is_business_hours/next_business_window, T022 dispatch_pending(), T023-T024 __init__ + runner step 4b, T025-T026 unit + integration tests
- Phase 6 (US4 P4: Audit Trail) — 5 tasks: T027 startup recovery, T028 api_list_email_events, T029 route registration, T030 dashboard history panel, T031 audit unit tests
- Phase 7 (Polish) — 3 tasks: T032 cycle_logger extension, T033 full test suite regression, T034 quickstart scenarios 1–6 manual validation

Key design decisions captured in tasks:
- ADR-0009 threading pattern cited explicitly in T004, T015, T022 (asyncio.to_thread() for HTTP handlers)
- ADR-0008 Gmail API send pattern cited in T020, T022
- Atomic write (tempfile + os.replace) required in T004, T014, T027
- ZoneInfo DST-aware scheduling required in T021, T025

Parallel opportunities documented per phase (e.g., T002+T003 parallel; T006+T010+T011+T012 parallel in Phase 3).

MVP scope: Phases 1–3 only (US1: auto-schedule) gives a working pipeline step 4a without any email actually being sent — safe, auditable, and immediately testable.

## Outcome

- ✅ Impact: tasks.md created; 34 concrete, independently-testable tasks covering full 007-email-scheduling scope
- 🧪 Tests: 4 unit test files (config, template, queue_store, scheduler) + 1 integration test file generated as tasks; minimum test case counts specified per task
- 📁 Files: 1 tasks file created at specs/007-email-scheduling/tasks.md
- 🔁 Next prompts: /sp.implement (start with T001 → T005, then T006-T013 for MVP)
- 🧠 Reflection: Session context compaction occurred during /sp.tasks execution; tasks were generated successfully in the resumed session. The queue_store.py and scheduler.py growth pattern (tasks added across phases) was documented explicitly in the Notes section to avoid confusion during implementation.

## Evaluation notes (flywheel)

- Failure modes observed: create-phr.sh not accessible from Bash tool (WSL path issue) — fallback to agent-native Write used
- Graders run and results (PASS/FAIL): all tasks follow required checklist format (checkbox, ID, [P], [Story], file path); all 34 tasks validated; no unresolved placeholders
- Prompt variant (if applicable): "null"
- Next experiment: "null"
