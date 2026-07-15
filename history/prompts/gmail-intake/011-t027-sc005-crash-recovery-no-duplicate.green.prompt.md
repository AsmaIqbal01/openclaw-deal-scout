---
id: 011
title: T027 SC-005 Crash Recovery No Duplicate Test
stage: green
date: 2026-07-15
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: implement T027
labels: ["sc-005","crash-recovery","systemexit","idempotency","integration-tests"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - tests/integration/test_check_new_deals.py
tests:
  - tests/integration/test_check_new_deals.py::test_sc005_crash_recovery_no_duplicate
---

## Prompt

implement T027

## Response snapshot

Added `test_sc005_crash_recovery_no_duplicate` to `tests/integration/test_check_new_deals.py`
(also added `MagicMock` to imports and `read_store` to state_store imports).

Test structure:
1. Crash run: classify side_effect=[_CLASSIFICATION_DEAL, SystemExit("kill")] — msg1 succeeds and
   is appended to store, then SystemExit is raised for msg2; caught with pytest.raises(SystemExit).
2. Intermediate assertion: read_store confirms msg1 is in state store (it was persisted before kill).
3. Recovery run: classify returns _CLASSIFICATION_DEAL for all; assert call_count==2 (msg1 pre-filtered).
4. result_ids == {"msg2","msg3"} — no msg1 in deals_extracted.
5. Final state store: exactly 1 entry with gmail_message_id=="msg1" (no duplicate).

Key insight: SystemExit inherits from BaseException, not Exception, so the bare `except Exception`
in server.py's per-message loop does not catch it. The finally block releases the lock; msg1 is
persisted only because append_message ran before the kill (after extract_payload succeeded).

36/36 full suite passing.

## Outcome

- ✅ Impact: T027 complete — SC-005 boundary condition verified; no duplicate on process-kill recovery
- 🧪 Tests: 1 new test (passes); full suite 36/36 green, no regressions
- 📁 Files: 1 modified (tests/integration/test_check_new_deals.py — docstring, imports, 1 test)
- 🔁 Next prompts: Phase 5 complete (T025-T027); Phase 6 tasks (T028 OAuth setup, T029 log audit, T030 FR-003a ordering, T031 SC-004 coverage)
- 🧠 Reflection: Two-run structure (crash + recovery) with intermediate state assertion makes the test self-documenting — each phase of the SC-005 scenario is independently verifiable

## Evaluation notes (flywheel)

- Failure modes observed: none — test passed on first run
- Graders run and results (PASS/FAIL): self-review PASS (correctness vs tasks.md, BaseException propagation confirmed, no-duplicate assertion explicit)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): extend to verify lock is released after SystemExit (assert no ConcurrentInvocationError on recovery run start)
