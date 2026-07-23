---
id: "0003"
title: Gateway Scheduler ADR Created
stage: plan
date: 2026-07-23
surface: agent
model: claude-sonnet-4-6
feature: 005-mcp-dashboard
branch: 005-mcp-dashboard
user: AsmaIqbal01
command: /sp.adr gateway-scheduler-architecture
labels: ["plan","adr","gateway","scheduler","threading","http-transport","mcp"]
links:
  spec: specs/005-mcp-dashboard/spec.md
  ticket: null
  adr: history/adr/0004-gateway-http-transport-replaces-stdio-subprocess-model.md
  pr: null
files:
  - history/adr/0004-gateway-http-transport-replaces-stdio-subprocess-model.md
  - history/adr/0005-gateway-scheduler-architecture-single-process-thread-model.md
tests:
  - null
---

## Prompt

/sp.adr gateway-scheduler-architecture

## Response snapshot

Ran check-prerequisites (feature: 005-mcp-dashboard). Found 3 existing ADRs (0001–0003). Extracted 7 decisions from research.md; 2 passed significance test: (1) HTTP transport superseding stdio model at orchestration layer, (2) single-process thread model for scheduler + HTTP. Created ADR-0004 (Gateway HTTP Transport) and ADR-0005 (Gateway Scheduler Architecture). ADR-0004 notes partial supersession of ADR-0001 at orchestration layer; individual step packages retain their existing interfaces.

## Outcome

- ✅ Impact: Two architecture decisions documented with full tradeoff analysis. ADR-0004 clarifies the evolution from stdio subprocess to HTTP transport; ADR-0005 documents the threading model and its constraints (asyncio nesting issue, blocking cycle behaviour, SIGTERM contract).
- 🧪 Tests: null
- 📁 Files: history/adr/0004-..., history/adr/0005-...
- 🔁 Next prompts: /sp.tasks
- 🧠 Reflection: The asyncio nesting rejection rationale in ADR-0005 (Alternative B) is the most important thing to document — it's non-obvious and will be the first thing a future developer tries to "improve." The ADR makes the reason explicit so the refactor attempt stops before it starts.

## Evaluation notes (flywheel)

- Failure modes observed: null
- Graders run and results (PASS/FAIL): Significance test — 2 PASS, 5 below threshold
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): /sp.tasks
