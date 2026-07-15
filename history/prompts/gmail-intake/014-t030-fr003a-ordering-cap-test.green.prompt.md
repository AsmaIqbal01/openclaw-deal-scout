---
id: 014
title: T030 FR-003a Ordering Cap Unit Test
stage: green
date: 2026-07-15
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: implement T030
labels: ["fr-003a","ordering","poll-inbox","gmail-client","unit-test"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - tests/unit/test_gmail_client.py
tests:
  - tests/unit/test_gmail_client.py::test_poll_inbox_cap_applied_oldest_first
---

## Prompt

implement T030

## Response snapshot

Created `tests/unit/test_gmail_client.py` with one FR-003a test. Mocked the Gmail service to return
60 messages (msg0 with internalDate=1000, msg59 with internalDate=6900). Called
`poll_inbox(service, since_ts=None, max_messages=50)`. Asserted:
- len(result) == 50
- result_dates == sorted(result_dates) (oldest-first order)
- min(result_dates) == 1000, max(result_dates) == 5900 (the 50 oldest, not 50 most-recent)
- result_ids.isdisjoint({msg50,...,msg59}) (10 most-recent excluded)

Cap-before-filter order confirmed in module docstring: poll_inbox returns the capped list;
server.py lines 110-113 apply the already_processed filter AFTER poll_inbox returns.

37/37 full suite passing.

## Outcome

- ✅ Impact: T030 complete — FR-003a ordering guarantee is regression-guarded by a unit test
- 🧪 Tests: 1 new (passes); full suite 37/37 green, no regressions
- 📁 Files: 1 new (tests/unit/test_gmail_client.py)
- 🔁 Next prompts: T031 (SC-004 coverage map in test_tool_contract.py)
- 🧠 Reflection: Using side_effect as a list on get().execute() correctly sequences the 60 full-message returns in stub order; the test is deterministic with no random shuffling needed

## Evaluation notes (flywheel)

- Failure modes observed: none — test passed on first run
- Graders run and results (PASS/FAIL): self-review PASS (FR-003a requirements verified, cap-before-filter documented)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): add pagination test — verify poll_inbox follows nextPageToken across multiple list() pages
