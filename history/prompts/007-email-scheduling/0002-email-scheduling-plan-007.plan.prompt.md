---
id: "0002"
title: Email Scheduling Plan 007
stage: plan
date: 2026-07-26
surface: agent
model: claude-sonnet-4-6
feature: 007-email-scheduling
branch: 007-email-scheduling
user: AsmaIqbal01
command: /sp.plan
labels: ["plan","email-scheduling","gmail-api","zoneinfo","threading","email-scheduler"]
links:
  spec: specs/007-email-scheduling/spec.md
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - specs/007-email-scheduling/plan.md
  - specs/007-email-scheduling/research.md
  - specs/007-email-scheduling/data-model.md
  - specs/007-email-scheduling/quickstart.md
  - specs/007-email-scheduling/contracts/email-scheduler-api.md
tests:
  - "null"
---

## Prompt

/sp.plan (empty input — current branch 007-email-scheduling)

## Response snapshot

Ran setup-plan.sh; spec scored 9.57/10 PASS (v21 after three revision passes).
Generated all five planning artifacts for feature 007-email-scheduling:

**plan.md** — 6 architectural decisions:
1. Gmail API `users().messages().send()` instead of raw SMTP — reuses existing google-api-python-client; native OAuth2 refresh
2. `zoneinfo.ZoneInfo("Europe/London")` for DST-aware business-hours gate — Python 3.12 stdlib, no new deps
3. `email_scheduler.auth.build_send_service()` duplicates credential pattern from gmail_intake — preserves "001 unchanged" spec constraint
4. `threading.Lock` + `asyncio.to_thread()` for queue write serialisation — prevents event-loop starvation
5. Step 4 split: 4a per-deal `schedule_for_deal()`, 4b single `dispatch_pending()` per cycle
6. `logging.FileHandler` for email_audit.log — thread-safe, consistent with CycleLogger pattern

New package `src/email_scheduler/` with 7 modules: config, models, queue_store, audit_logger, template, auth, scheduler.

Modified packages: `pipeline_orchestrator.runner` (step 4a/4b), `openclaw_gateway.server` (4 new routes), `openclaw_gateway.routes.email_api` (new file).

All 6 Constitution Check gates PASS. No paid deps, no new intake source, runtime headless, deduplication via gmail_message_id, email_scheduler is independent module, FR-017 no-raise contract.

Two ADR suggestions surface: gmail-api-send-vs-smtp, email-dispatch-threading-model.

## Outcome

- ✅ Impact: 007-email-scheduling plan complete — all 5 artifacts generated; implementation-ready
- 🧪 Tests: none yet (plan stage)
- 📁 Files: 5 files created (plan.md, research.md, data-model.md, quickstart.md, contracts/email-scheduler-api.md)
- 🔁 Next prompts: /sp.adr gmail-api-send-vs-smtp, /sp.adr email-dispatch-threading-model, /sp.tasks
- 🧠 Reflection: Spec v21 took 3 scorer passes (8.7 → 9.0 → 9.57) before PASS; key ambiguities resolved were total-field semantics in GET endpoints, whitespace-only field absence definition, file path env vars, and OAuth module reference

## Evaluation notes (flywheel)

- Failure modes observed: spec required 3 revision passes before reaching 9.5 threshold; each pass addressed a distinct ambiguity cluster (response field semantics, file paths, credential module reference)
- Graders run and results (PASS/FAIL): spec-scorer 9.57/10 PASS after v21 revision
- Prompt variant (if applicable): "null"
- Next experiment: "null"
