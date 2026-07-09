---
id: "006"
title: Gmail Intake Tasks Generated
stage: tasks
date: 2026-07-09
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: /sp.tasks
labels: ["tasks","gmail-intake","fastmcp","python","tdd","state-store","classifier","extractor"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: history/adr/0001-python-fastmcp-subprocess-runtime.md
  pr: null
files:
  - specs/001-gmail-intake/tasks.md
tests:
  - tests/unit/test_state_store.py (planned T018, T025)
  - tests/unit/test_classifier.py (planned T019)
  - tests/unit/test_extractor.py (planned T023)
  - tests/integration/test_check_new_deals.py (planned T026, T027)
  - tests/contract/test_tool_contract.py (planned T024)
---

## Prompt

/sp.tasks

## Response snapshot

Generated `specs/001-gmail-intake/tasks.md` with 33 tasks across 6 phases.

**Phase structure**:
- Phase 1: Setup — 5 tasks (directory structure, pyproject.toml, .env.example, .gitignore, data/.gitkeep)
- Phase 2: Foundational — 2 tasks (package __init__.py, models.py with 5 dataclasses + 4 exception classes)
- Phase 3: P1 Unattended Deal Detection — 12 tasks (state_store.py x4, gmail_client.py x2, classifier.py, extractor.py metadata, server.py skeleton + wire, tests x2)
- Phase 4: P2 Structured Deal Data Extraction — 5 tasks (FR-011 truncate_summary, FR-010 truncate_excerpt, extract_payload, test_extractor.py, test_tool_contract.py)
- Phase 5: P3 Idempotent Re-runs — 3 tasks (crash-recovery unit tests, integration idempotency tests, SC-005 mid-poll kill test)
- Phase 6: Polish — 6 tasks (setup_oauth.py, log audit, FR-003a ordering, SC-004 boundary coverage, full test run, live smoke test)

**MVP scope**: Phase 3 complete (T001–T019) delivers a working check_new_deals MCP tool passable against US1 acceptance test.

**Key task decisions**:
- Phase 3 implements state_store.py WITH atomic writes and exclusive lock from the start (correctness requirement, not just an US3 concern); Phase 5 adds tests that VERIFY the guarantee
- FR-011 sentence-boundary regex (research.md Decision 8) moved to Phase 4 (US2) since it's an extraction-quality concern, not a detection concern
- SC-004's 13 boundary conditions mapped to specific test tasks; T031 documents the mapping in test file comments

## Outcome

- ✅ Impact: Complete, immediately executable task list for the gmail-intake feature; 33 tasks with exact file paths; 10 identified parallel opportunities; MVP scope clearly bounded to Phase 3.
- 🧪 Tests: 5 test files planned with specific test function names; all SC-004 boundary conditions mapped to test tasks
- 📁 Files: specs/001-gmail-intake/tasks.md
- 🔁 Next prompts: git checkpoint to commit tasks.md; then begin implementation with T001 (project structure)
- 🧠 Reflection: The idempotency implementation (atomic writes + lock) belongs in Phase 3 for correctness, but the TESTS that prove idempotency belong in Phase 5 for user story alignment. This split avoids the awkward choice between implementing something in the wrong phase vs testing something before its user story is "due".

## Evaluation notes (flywheel)

- Failure modes observed: none — design documents were complete enough that task derivation was straightforward
- Graders run and results (PASS/FAIL): format validation — all 33 tasks follow checklist format (checkbox + ID + labels + file path)
- Prompt variant (if applicable): standard /sp.tasks with no extra args
- Next experiment: execute Phase 1–2 tasks and verify checkpoint passes before starting Phase 3
