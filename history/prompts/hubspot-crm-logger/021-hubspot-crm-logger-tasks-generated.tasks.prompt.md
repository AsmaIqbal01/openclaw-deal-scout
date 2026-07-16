---
id: "021"
title: HubSpot CRM Logger Tasks Generated
stage: tasks
date: 2026-07-16
surface: agent
model: claude-sonnet-4-6
feature: 002-hubspot-crm-logger
branch: 002-hubspot-crm-logger
user: AsmaIqbal000
command: /sp.tasks
labels: ["tasks","hubspot","crm","tdd","rate-limit","idempotency","state-store"]
links:
  spec: specs/002-hubspot-crm-logger/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/002-hubspot-crm-logger/tasks.md
tests:
  - 46 task items generated; test tasks T007, T009, T010, T018, T019, T023, T027, T030-T034 written before implementation tasks
---

## Prompt

/sp.tasks (no args — feature context from current branch 002-hubspot-crm-logger)

## Response snapshot

Generated `specs/002-hubspot-crm-logger/tasks.md` with 46 tasks across 8 phases covering all 5 user stories.

**Phase 1 — Setup (T001–T003, 3 tasks)**: Package scaffold (`src/crm_logger/__init__.py`), dependency registration (`requests>=2.31`), test stub files.

**Phase 2 — Foundational (T004–T008, 5 tasks)**: `models.py` (7 dataclasses + 5 exceptions), `state_store.py` (6 functions with merge-write), `client.py` (HubSpotClient skeleton + `_call()` + 100ms delay + call counter), unit tests for state_store, `split_name()` + `truncate_dealname()` helpers.

**Phase 3 — US1 P1 (T009–T017, 9 tasks)**: HubSpotClient tests + log_deal happy-path tests; `search_contact()`, `upsert_contact()`, `create_deal()` (with embedded association in deal body → 3 calls/deal exactly), `log_deal()` FR-002 gate, `run_crm_cycle()` basic loop, `sync_deals_to_crm` MCP tool.

**Phase 4 — US2 P1 (T018–T022, 5 tasks)**: FR-007 error-path tests; all-failure-type catching in `log_deal()` (network, 4xx, 5xx, missing ID, invalid_sender_email → crm-pending + WARN); FR-013 state-store write failure handling (ERROR log, stay crm-pending).

**Phase 5 — US3 P2 (T023–T026, 4 tasks)**: Sleep timing test; FR-006 DEBUG log per call (msg_id + call_type passed through); FR-011 circuit breaker check in `run_crm_cycle()` (client.call_count >= 90 → defer remainder to crm-pending).

**Phase 6 — US4 P2 (T027–T029, 3 tasks)**: Drain-order test; update `run_crm_cycle()` to call `get_pending_deals()` before `get_new_deals()`.

**Phase 7 — US5 P2 (T030–T041, 12 tasks)**: Circuit breaker tests (31 deals → 30 written + 1 crm-pending); split_name/truncation tests; 401 cycle counter tests (qualifying cycle / mixed cycle / zero-call cycle / suspension at 3 / restart reset); FR-015 payload persistence tests; implementation: within-cycle 401 abort, cross-cycle 401 counter, suspension mode bypass, split_name wiring, cross-feature `gmail_intake` changes (state_store merge-write + extra_fields, server.py 9-field write, models.py Literal extension).

**Phase 8 — Polish (T042–T046, 5 tasks)**: Integration test (HubSpot sandbox), full unit suite, smoke test, OpenClaw MCP config verification, full test suite.

## Outcome

- ✅ Impact: 46 tasks ready for /sp.implement — all 5 user stories covered; MVP is US1+US2 (phases 3+4)
- 🧪 Tests: 14 test tasks (T007, T009, T010, T018, T019, T023, T027, T030–T034) written before implementation; TDD flow enforced by FAIL-then-PASS instructions
- 📁 Files: specs/002-hubspot-crm-logger/tasks.md
- 🔁 Next prompts: /sp.implement for 002-hubspot-crm-logger
- 🧠 Reflection: Key sequencing insight: US3 (rate limiting) and US4 (drain order) can be worked in parallel after Phase 2 since they touch different parts of the orchestrator. US5 must come after US2 because the 401 cross-cycle handling builds on the error-path logic from US2. The cross-feature `gmail_intake` changes (T039–T041) are cleanly isolated to the end of US5 and require regression-testing 001's existing unit tests.

## Evaluation notes (flywheel)

- Failure modes observed: None — task generation completed from design docs without ambiguity
- Graders run and results (PASS/FAIL): Format validation — all 46 tasks follow `- [ ] T### [P?] [US?] Description with file path` format
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Run /sp.implement starting with Phase 1 + Phase 2 MVP (T001–T016)
