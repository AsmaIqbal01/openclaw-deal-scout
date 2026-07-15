---
id: 008
title: T024 Contract Tests for check_new_deals_handler
stage: green
date: 2026-07-15
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: implement T024
labels: ["contract-tests","tool-contract","check_new_deals_handler","pytest-asyncio"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - tests/contract/__init__.py
  - tests/contract/test_tool_contract.py
tests:
  - tests/contract/test_tool_contract.py::test_return_shape_ok
  - tests/contract/test_tool_contract.py::test_status_is_valid_value
  - tests/contract/test_tool_contract.py::test_deals_extracted_is_list
  - tests/contract/test_tool_contract.py::test_count_identity_ok
  - tests/contract/test_tool_contract.py::test_deal_payload_all_nine_fields
  - tests/contract/test_tool_contract.py::test_return_shape_error
  - tests/contract/test_tool_contract.py::test_count_identity_empty_inbox
---

## Prompt

implement T024

## Response snapshot

Created `tests/contract/__init__.py` and `tests/contract/test_tool_contract.py` with 7 async contract
tests for `check_new_deals_handler()`. Two pytest fixtures (`ok_pipeline`, `empty_inbox_pipeline`)
patch all 12 server-level callsites via `ExitStack`. Tests verify: exact 5-key return shape, status
constrained to {"ok","error"}, `deals_extracted` always a list, count identity
`processed_count == len(deals_extracted) + skipped_count`, all 9 DealPayload fields with correct types
(key set asserted via `dataclasses.fields(DealPayload)`), and error-path shape. 28/28 suite passing.

## Outcome

- ✅ Impact: T024 complete — tool contract surface is now regression-guarded by 7 async tests
- 🧪 Tests: 7 new (all pass); full suite 28/28 green, no regressions
- 📁 Files: 2 new files (tests/contract/__init__.py, tests/contract/test_tool_contract.py)
- 🔁 Next prompts: T025 (test_state_store crash-recovery + pre-filter), T026 (integration tests), T027 (SC-005 crash scenario)
- 🧠 Reflection: ExitStack + return_value mocking kept fixtures concise without pytest-mock dependency; _DEAL_PAYLOAD_FIELDS derived from live dataclass ensures the field-set check stays in sync with models.py

## Evaluation notes (flywheel)

- Failure modes observed: none — all 7 tests passed on first run
- Graders run and results (PASS/FAIL): self-review PASS (correctness vs tasks.md, no TODOs, no secrets, type alignment)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): add a skipped_count > 0 scenario (non-deal classified message) to strengthen count identity coverage
