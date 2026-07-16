---
id: "022"
title: ADR CRM Failable Pending Circuit Breaker
stage: misc
date: 2026-07-16
surface: agent
model: claude-sonnet-4-6
feature: 002-hubspot-crm-logger
branch: 002-hubspot-crm-logger
user: AsmaIqbal000
command: /sp.adr
labels: ["adr","crm","failable-pending","circuit-breaker","rate-limit","retry","discord"]
links:
  spec: specs/002-hubspot-crm-logger/spec.md
  ticket: null
  adr: history/adr/0003-crm-write-failable-pending-and-circuit-breaker.md
  pr: null
files:
  - history/adr/0003-crm-write-failable-pending-and-circuit-breaker.md
tests:
  - null
---

## Prompt

Document the cross-cutting architectural decision for the CRM write queue, retry/pending-state, and circuit-breaker pattern used in 002-hubspot-crm-logger (covers US2, US3, US5 — tasks T018-T022, T023-T029, T030-T041). Follow the same format as ADR-0001 and ADR-0002 from 001-gmail-intake. Explicitly note whether this pattern applies to Step 3 (Discord Notification) as well, since notification failures may need similar retry/pending semantics.

## Response snapshot

Created `history/adr/0003-crm-write-failable-pending-and-circuit-breaker.md` documenting five integrated decisions:

1. **Failable-pending state**: any HubSpot write failure → `crm-pending` entry in state store with all 9 DealPayload fields persisted; never silent drop; never crash.
2. **Drain-first retry ordering**: `run_crm_cycle()` processes `crm-pending` entries before `deal_extracted` entries each cycle; prevents starvation.
3. **100ms inter-call delay**: `time.sleep(0.1)` in `HubSpotClient._call()` after every non-401 response; enforced at a single point; yields ≤10 calls/second.
4. **90-call per-cycle circuit breaker**: `client.call_count >= 90` check before each deal; remaining deals written to `crm-pending` and cycle exits with WARN.
5. **Consecutive-401 suspension gate**: `consecutive_401_cycles` counter in state store; 3 consecutive qualifying cycles → FATAL log + suspend all CRM writes; restart resets counter to 0 with WARN.

**Applicability to 003 (Discord Notification)**: explicitly documented in a cross-feature table. The same failable-pending + drain-first + circuit-breaker pattern SHOULD be adopted in 003's plan. Discord's rate-limit parameters differ (lower per-webhook frequency than HubSpot's burst cap) but the structural template is directly reusable. Constitution Principle VI already names `crm-logged-notify-pending` as the parallel Discord failure state.

**Alternatives rejected**: synchronous in-cycle retry (blocks cycle on sustained outage), silent drop (permanent data loss), agent crash (violates Principle VI), separate DLQ file (second lock + consistency risk), no 401 suspension (floods HubSpot with bad-credential calls).

## Outcome

- ✅ Impact: Cross-cutting failure-handling pattern documented as ADR-0003; provides template for 003-discord-notification planning
- 🧪 Tests: null
- 📁 Files: history/adr/0003-crm-write-failable-pending-and-circuit-breaker.md
- 🔁 Next prompts: /sp.implement for 002-hubspot-crm-logger (start with T001–T016 MVP phases)
- 🧠 Reflection: Grouping all three mechanisms (failable-pending, rate-limiting, 401 suspension) into one ADR was the right call — they share the same root design: defer-to-state rather than retry-in-place. The cross-feature applicability note for 003 closes the loop opened in the /sp.plan ADR suggestion.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): Format check vs ADR-0001/ADR-0002 — PASS (same section structure: Status/Date/Feature/Context, Decision, Consequences, Alternatives Considered, References)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Confirm 003-discord-notification spec explicitly adopts `notify-pending` outcome following this ADR
