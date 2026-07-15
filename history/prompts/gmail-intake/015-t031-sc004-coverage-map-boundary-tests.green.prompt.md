---
id: 015
title: T031 SC-004 Coverage Map and Boundary Tests
stage: green
date: 2026-07-15
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: implement T031
labels: ["sc-004","boundary-tests","coverage-map","integration","unit-test"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - tests/contract/test_tool_contract.py
  - tests/integration/test_check_new_deals.py
  - tests/unit/test_extractor.py
  - tests/unit/test_state_store.py
tests:
  - tests/integration/test_check_new_deals.py::test_auth_error_returns_status_error
  - tests/integration/test_check_new_deals.py::test_gmail_rate_limit_aborts_cycle
  - tests/integration/test_check_new_deals.py::test_invalid_internal_date
  - tests/integration/test_check_new_deals.py::test_body_absent_skipped
  - tests/integration/test_check_new_deals.py::test_network_failure_mid_poll
  - tests/integration/test_check_new_deals.py::test_unhandled_exception_continues
  - tests/unit/test_extractor.py::test_missing_from_header
  - tests/unit/test_extractor.py::test_missing_subject_header
  - tests/unit/test_state_store.py::test_append_message_write_failure
---

## Prompt

implement T031

## Response snapshot

Added SC-004 boundary coverage map to `tests/contract/test_tool_contract.py` docstring (13-entry
table mapping each condition to its test and file). Added 9 new tests for the 8 previously uncovered
boundary conditions:

**Integration tests (tests/integration/test_check_new_deals.py):**
- `test_auth_error_returns_status_error` (#1): mocks build_service to raise AuthError → verifies status='error'
- `test_gmail_rate_limit_aborts_cycle` (#2): mocks poll_inbox to raise HttpError(429) → status='error'
- `test_invalid_internal_date` (#6): mocks extract_metadata to raise InvalidMetadataError → skipped_count=1, status='ok'
- `test_body_absent_skipped` (#8): mocks extract_body to return None → skipped_count=1, status='ok'
- `test_network_failure_mid_poll` (#9): mocks poll_inbox to raise ConnectionError → status='error'
- `test_unhandled_exception_continues` (#10): extract_body raises RuntimeError for msg-crash; msg-ok
  processed normally → processed_count=2, skipped_count=1, 1 deal extracted, count identity holds

**Unit tests:**
- `test_missing_from_header` and `test_missing_subject_header` (#7): call real extract_metadata with
  a msg dict missing the From or Subject header → InvalidMetadataError raised
- `test_append_message_write_failure` (#12): patches os.replace to raise OSError → append_message
  does not raise, canonical store file not created

Conditions already covered (no new test needed): #3 (T019), #4 (T019), #5 (T023), #11 (T018), #13 (T026).

46/46 tests passing.

## Outcome

- ✅ Impact: T031 complete — all 13 SC-004 boundary conditions are regression-guarded and documented
- 🧪 Tests: 9 new (all pass); full suite 46/46 green, no regressions
- 📁 Files: 4 modified (test_tool_contract.py docstring, test_check_new_deals.py +6, test_extractor.py +2, test_state_store.py +1)
- 🔁 Next prompts: T032 (run full test suite confirm all pass), T033 (live smoke test via MCP inspector)
- 🧠 Reflection: The test_unhandled_exception_continues test is the most interesting — it confirms the outer `except Exception` in server.py:221 catches RuntimeError but not SystemExit, and that the handler continues to the next message. Using real extract_payload (not mocked) validates the full pipeline for msg-ok.

## Evaluation notes (flywheel)

- Failure modes observed: none — all 9 new tests passed on first run
- Graders run and results (PASS/FAIL): self-review PASS (all 13 SC-004 conditions mapped, assertions verified against server.py source)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): add a test for SC-004 #6 with internalDate="0" (zero value) to verify extract_metadata rejects it at line 77-78
