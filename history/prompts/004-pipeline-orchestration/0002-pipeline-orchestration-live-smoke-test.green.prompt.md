---
id: "0002"
title: Pipeline Orchestration Live Smoke Test
stage: green
date: 2026-07-23
surface: agent
model: claude-sonnet-4-6
feature: 004-pipeline-orchestration
branch: main
user: AsmaIqbal01
command: run a live smoke test
labels: ["green","smoke-test","e2e","orchestrator","gmail","hubspot","discord","gemini-429"]
links:
  spec: specs/004-pipeline-orchestration/spec.md
  ticket: null
  adr: null
  pr: https://github.com/AsmaIqbal01/openclaw-deal-scout/pull/5
files:
  - src/pipeline_orchestrator/__main__.py
  - src/pipeline_orchestrator/runner.py
  - src/pipeline_orchestrator/scheduler.py
tests:
  - Live E2E: SCHEDULER_MODE=systemd python3.12 -m pipeline_orchestrator (real Gmail + Gemini + HubSpot + Discord)
---

## Prompt

run a live smoke test

## Response snapshot

Ran `SCHEDULER_MODE=systemd python3.12 -m pipeline_orchestrator` against the real inbox, sourcing `.env`. Single-cycle one-shot invocation; exited with code 0.

**Timeline**: 2026-07-23T00:08:17Z → 00:14:56Z (~6.5 min)

**Step 1 — Gmail intake**: 22 messages fetched. Gemini 2.5 Flash classified sequentially. Multiple Gemini 429 bursts absorbed by the existing back-off retry logic (10s → 30s → 60s). 2 messages ultimately skipped after retries exhausted (classifier rate-limited — skipped). 1 deal extracted: `gmail_message_id=19f8ab0ea26e677c`.

**Step 2 — HubSpot CRM logger**: Deal logged to HubSpot — `deal_id=337701952242`. `crm-logged` outcome confirmed in log.

**Step 3 — Discord notifier**: Discord notification sent for `19f8ab0ea26e677c`. Confirmed in log.

**Exit**: code 0. Clean shutdown. No stale `.pipeline.lock`.

## Outcome

- ✅ Impact: Full 3-step pipeline runs end-to-end unattended. First live confirmation of orchestrator wiring, SIGTERM-safe exit, and cycle-summary emission.
- 🧪 Tests: Live E2E against real Gmail, Gemini, HubSpot, Discord — 1 deal extracted, CRM-logged, Discord-notified
- 📁 Files: No code changes — smoke test only
- 🔁 Next prompts: Activate systemd timer for unattended scheduling (`deploy/README.md`)
- 🧠 Reflection: Gemini free-tier burst limit caused multiple 429s across a 22-message batch (~6.5 min for one cycle). The classifier's exponential back-off absorbed all of them without crashing; 2 messages hit the retry ceiling and were skipped. This is expected FR-005 / SC-002 behaviour. HubSpot and Discord both succeeded on the first attempt — no pending state left in the store. The orchestrator's FR-022 logic (continue steps 2+3 even after partial step 1 abort) was not triggered here since step 1 completed fully.

## Evaluation notes (flywheel)

- Failure modes observed: Gemini 429 burst (free-tier RPM limit) mid-batch — handled gracefully; 2 messages skipped cleanly
- Graders run and results (PASS/FAIL): Live E2E — PASS (exit 0, deal in HubSpot, Discord notified)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Run with MAX_MESSAGES_PER_POLL=5 to reduce Gemini burst pressure and confirm all messages are classified without 429 skips
