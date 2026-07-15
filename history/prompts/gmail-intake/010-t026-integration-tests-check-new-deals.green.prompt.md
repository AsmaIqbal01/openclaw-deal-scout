---
id: 010
title: T026 Integration Tests for check_new_deals_handler
stage: green
date: 2026-07-15
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: implement T026
labels: ["integration-tests","idempotency","pre-filter","concurrent-invocation","crash-recovery"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - tests/integration/__init__.py
  - tests/integration/test_check_new_deals.py
tests:
  - tests/integration/test_check_new_deals.py::test_idempotent_rerun
  - tests/integration/test_check_new_deals.py::test_already_processed_pre_filter
  - tests/integration/test_check_new_deals.py::test_concurrent_invocation_rejected
  - tests/integration/test_check_new_deals.py::test_process_kill_recovery
---

## Prompt

implement T026

## Response snapshot

Created `tests/integration/__init__.py` and `tests/integration/test_check_new_deals.py` with 4 async
integration tests. Tests use a real on-disk state store (tmp_path) and real lock mechanism; only Gmail
API and Gemini API calls are mocked. extract_payload runs for real in all tests. A shared `_patches()`
helper sets up all external-service mocks and env vars; individual tests enter_context the classify mock
separately when they need to assert call counts.

- test_idempotent_rerun: 3-message inbox called twice; second call processed_count=0, deals_extracted=[]
- test_already_processed_pre_filter: seeded msg-x in store; classify called exactly 2 times (msg-x skipped)
- test_concurrent_invocation_rejected: real lock held before handler; status=error, error_details='concurrent invocation'
- test_process_kill_recovery: msg1+msg2 seeded; Gmail returns all 3; only msg3 classified; call_count==1

35/35 full suite passing.

## Outcome

- ✅ Impact: T026 complete — US3 idempotency guarantees validated end-to-end with a real state store
- 🧪 Tests: 4 new integration tests (all pass); full suite 35/35 green, no regressions
- 📁 Files: 2 new files (tests/integration/__init__.py, tests/integration/test_check_new_deals.py)
- 🔁 Next prompts: T027 (SC-005 crash scenario — SystemExit mid-classify, no duplicate on recovery)
- 🧠 Reflection: Running extract_payload for real (not mocked) gave the integration tests more fidelity — it exercised the full metadata→DealPayload mapping rather than returning a pre-built fixture

## Evaluation notes (flywheel)

- Failure modes observed: none — all 4 tests passed on first run
- Graders run and results (PASS/FAIL): self-review PASS (correctness vs tasks.md, real state store, call-count assertions)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): add test for Gmail network error mid-poll aborting the cycle (SC-004 boundary #9)
