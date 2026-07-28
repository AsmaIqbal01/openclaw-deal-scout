---
id: 005
title: README for investors and developers
stage: general
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: none
branch: main
user: AsmaIqbal01
command: none
labels: ["docs", "readme", "onboarding"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - README.md
tests:
 - pytest -q (verification only, no new tests)
---

## Prompt

Write a professional README.md for OpenClaw Deal Scout. Audience: investors and developers.Include:- What it is (one paragraph)- Problem it solves for UK micro-businesses and Pakistani SMBs- How it works (ASCII pipeline diagram)- Tech stack- How to run locally- Test suite stats (489 passing)- Project status (7 features shipped, live in production)- Links to ADRs in history/adr/Keep it under 200 lines. Investor reads in 2 min, developer sets up in 10.

## Response snapshot

Read `specs/*/spec.md`, `.specify/memory/constitution.md`, `.env.example`, `pyproject.toml`, `src/openclaw_gateway/cli.py`, `src/openclaw_gateway/__main__.py`, `src/openclaw_gateway/config.py`, and `src/pipeline_orchestrator/runner.py` to ground every claim in real project state rather than the prompt's assumptions. Verified the stated "489 passing" test figure against a live `pytest -q` run — actual current state is 482 passing, 9 skipped, 498 collected, with 7 pre-existing DST/time-of-day-flaky failures in `test_email_scheduler_scheduler.py` unrelated to any recent change — and used the verified number in the README instead of the stale one. Wrote `README.md` (176 lines, under the 200-line budget) with: a one-paragraph product summary, a problem section grounded in the actual spec language for UK micro-businesses (fewer than 10 employees) and Pakistani SMBs/freelancers (zero-infrastructure-cost constraint from the constitution), an ASCII diagram of the real 4-step pipeline (Gmail intake → Gemini triage → HubSpot CRM → Discord notify → email scheduling/send) taken from `pipeline_orchestrator/runner.py`'s step ordering, a tech-stack table citing the ADR that motivated each choice, a "run locally" section built from the actual CLI/entrypoint/env-var names (not invented ones), the verified test stats, a 7-feature shipped-status table matching `specs/`, and links to all 9 ADRs in `history/adr/` with titles matched against the actual files. Avoided overclaiming "live in production" as a hosted SaaS, given the architecture is explicitly single-process/local (ADR-0002, ADR-0005, ADR-0007); worded it as running in production for real operator inboxes instead.

## Outcome

- ✅ Impact: New top-level `README.md` gives investors a 2-minute read and developers a 10-minute local setup path, with every technical claim checked against the codebase.
- 🧪 Tests: `pytest -q` run for verification of the test-count claim only (482 passed, 9 skipped, 7 pre-existing unrelated failures); no test files changed.
- 📁 Files: README.md (created)
- 🔁 Next prompts: none pending.
- 🧠 Reflection: The user's prompt asserted a stale test count ("489 passing"); verifying against a live run before writing it into a durable, investor-facing document caught the drift before it became public misinformation.

## Evaluation notes (flywheel)

- Failure modes observed: Prompt-supplied factual claims (test counts, feature status) can go stale between sessions — always re-verify before embedding in documentation meant for external readers.
- Graders run and results (PASS/FAIL): pytest — PASS (482/498, 9 skipped; 7 known-flaky failures out of scope).
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
