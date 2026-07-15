---
id: 013
title: T029 Log Audit Verbosity Fixes
stage: refactor
date: 2026-07-15
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: implement T029
labels: ["log-audit","verbosity","state-store","gmail-client","observability"]
links:
  spec: specs/001-gmail-intake/plan.md
  ticket: null
  adr: null
  pr: null
files:
  - src/gmail_intake/state_store.py
  - src/gmail_intake/gmail_client.py
tests: []
---

## Prompt

implement T029

## Response snapshot

Audited all log statements across server.py, state_store.py, gmail_client.py, classifier.py,
extractor.py against T029 verbosity spec. Found 2 mismatches; fixed both.

**Mismatch 1 — state_store.py line 113**
- Before: `logger.error("state store write failed: %s", exc)`
- After: `logger.warning("state store write failed: %s", exc)`
- Reason: T029 lists "state store write failure" under WARN. Write failure is recoverable (message
  re-evaluated next run), so WARN is semantically correct.

**Mismatch 2 — gmail_client.py line 96**
- Before: `except (HttpError, ConnectionError): logger.warning("network failure mid-poll")`
- After: Split into HttpError (check resp.status == 429 → WARN; else → ERROR) and ConnectionError (ERROR)
- Reason: T029 lists "network failure mid-poll" under ERROR but "rate limit FR-017" under WARN.
  Combining them in one handler would log Gmail 429 at ERROR, violating FR-017. Split allows correct
  level per failure type.

All other log statements verified correct:
- server.py: DEBUG (poll cycle start/end), INFO (invoked, empty, body_absent, not_a_deal),
  logger.exception ERROR (unhandled per-message) ✅
- state_store.py: ERROR (read failures), WARN (malformed poll time, concurrent invocation,
  >50 MB, write failure after fix) ✅
- gmail_client.py: ERROR (all token/credential failures), WARN (429) / ERROR (other) after fix ✅
- classifier.py: WARN (rate-limited, non-429 errors, parse error) ✅

36/36 tests passing.

## Outcome

- ✅ Impact: T029 complete — all log statements now match T029 verbosity spec
- 🧪 Tests: 0 new; full suite 36/36 green, no regressions
- 📁 Files: 2 modified (state_store.py line 113, gmail_client.py lines 95-101)
- 🔁 Next prompts: T030 (FR-003a ordering assertion), T031 (SC-004 coverage map)
- 🧠 Reflection: The gmail_client split was necessary to avoid logging Gmail rate limits at ERROR — the single combined except block couldn't satisfy both T029 requirements simultaneously

## Evaluation notes (flywheel)

- Failure modes observed: none after fix — all 36 tests green
- Graders run and results (PASS/FAIL): self-review PASS (all 5 modules audited against T029 table)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): add a structured log field (e.g. exc_type) to WARN/ERROR statements for easier log filtering in production
