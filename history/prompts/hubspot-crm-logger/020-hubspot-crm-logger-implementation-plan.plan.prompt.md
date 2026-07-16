---
id: "020"
title: HubSpot CRM Logger Implementation Plan
stage: plan
date: 2026-07-16
surface: agent
model: claude-sonnet-4-6
feature: 002-hubspot-crm-logger
branch: 002-hubspot-crm-logger
user: AsmaIqbal000
command: /sp.plan
labels: ["plan","hubspot","crm","state-store","rate-limit","idempotency","mcp"]
links:
  spec: specs/002-hubspot-crm-logger/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/002-hubspot-crm-logger/plan.md
  - specs/002-hubspot-crm-logger/research.md
  - specs/002-hubspot-crm-logger/data-model.md
  - specs/002-hubspot-crm-logger/quickstart.md
  - specs/002-hubspot-crm-logger/contracts/crm-logger-contract.md
tests:
  - Constitution Check gates (all 6 evaluated — 5 PASS, 1 N/A)
---

## Prompt

/sp.plan (no args — feature context from current branch 002-hubspot-crm-logger)

## Response snapshot

Executed full /sp.plan workflow for 002-hubspot-crm-logger. Generated 5 artifacts:

**research.md** (Phase 0): 9 decisions resolved — (1) requests library over hubspot-api-client SDK for 4 targeted REST calls; (2) v3 endpoints for CRUD, association embedded in deal create body (not a 4th call — keeps per-deal count at exactly 3, matching FR-006/SC-006); (3) time.sleep(0.1) centralized in HubSpotClient._call() post-response; (4) two-layer backward-compatible state store extension (merge-write in 001, raw JSON reads in 002); (5) 6-module crm_logger package; (6) received_at → Unix epoch ms via datetime.fromisoformat(); (7) zero-param sync_deals_to_crm MCP tool; (8) lowest-ID contact on multi-match; (9) suspension bypass in orchestrator.py, not log_deal.

**data-model.md** (Phase 1): CrmStateStore, CrmMessage (raw dict with 9 DealPayload fields), HubSpotContact (with split_name() rule), HubSpotDeal (with truncate_dealname() and to_epoch_ms()), HubSpotWriteResult, CrmCycleResult, 5 exception classes. Full state transition diagram including ConsecutiveAuthFailureCounter state machine. Cross-feature changes to gmail_intake documented.

**contracts/crm-logger-contract.md** (Phase 1): MCP tool sync_deals_to_crm (3 response variants: ok/suspended/error); log_deal() signature with preconditions, return values, raises, invariants, log output; state_store contract (5 functions); HubSpotClient contract (_call() behaviour, 4 methods, call counter).

**quickstart.md** (Phase 1): 7-step setup (HubSpot account, private app + 8 scopes, 5 custom deal properties, pip install requests, OpenClaw MCP config, smoke test, first real run). Troubleshooting table for 6 failure modes.

**plan.md**: Technical Context, Constitution Check (5 PASS + 1 N/A), project structure (source + docs + tests), 3-phase implementation plan, architectural decision cross-reference table.

## Outcome

- ✅ Impact: Full implementation plan ready for /sp.tasks — 5 design artifacts created, all Constitution gates cleared
- 🧪 Tests: Constitution Check gates evaluated (5 PASS, 1 N/A); no unresolved NEEDS CLARIFICATION items
- 📁 Files: plan.md, research.md, data-model.md, quickstart.md, contracts/crm-logger-contract.md
- 🔁 Next prompts: /sp.tasks for 002-hubspot-crm-logger
- 🧠 Reflection: Key insight: embedding the deal-to-contact association in the deal create body (via `associations` field in v3 API) keeps the per-deal call count at exactly 3, matching FR-006 and SC-006. The two-layer state store extension strategy (merge-write in 001, raw JSON reads in 002) achieves backward compatibility without polluting ProcessedMessage with Optional fields. The suspension bypass in orchestrator.py rather than log_deal() keeps log_deal() pure and trivially unit-testable.

## Evaluation notes (flywheel)

- Failure modes observed: None — all 9 research decisions resolved from spec + existing codebase context without dispatching external research agents
- Graders run and results (PASS/FAIL): Constitution Check — PASS (5/5 gates; 1 N/A)
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Run /sp.tasks to generate dependency-ordered implementation tasks
