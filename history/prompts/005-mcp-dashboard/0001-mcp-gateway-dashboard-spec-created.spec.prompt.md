---
id: "0001"
title: MCP Gateway Dashboard Spec Created
stage: spec
date: 2026-07-23
surface: agent
model: claude-sonnet-4-6
feature: 005-mcp-dashboard
branch: 005-mcp-dashboard
user: AsmaIqbal01
command: /sp.specify
labels: ["spec","mcp","dashboard","gateway","openclaw","cli","doctor"]
links:
  spec: specs/005-mcp-dashboard/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/005-mcp-dashboard/spec.md
  - specs/005-mcp-dashboard/checklists/requirements.md
tests:
  - null
---

## Prompt

/sp.specify ## Feature: OpenClaw proper MCP orchestrator + dashboard (Option B rebuild)### ContextOpenClaw Deal Scout is a 4-step AI pipeline (Gmail → Gemini → HubSpot → Discord)that is currently LIVE in production via systemd timer. All business logic existsand is test/output contracts- [ ] Dashboard shows status, deals, quota, and run button- [ ] Existing tests still pass- [ ] openclaw gateway status command works- [ ] openclaw doctor command works- [ ] Claude Code is not referenced anywhere in production pipeline code

## Response snapshot

Created branch `005-mcp-dashboard` (next after 004-pipeline-orchestration). Wrote `specs/005-mcp-dashboard/spec.md` with 5 user stories, 20 functional requirements across gateway/CLI/dashboard/regression-gate groups, 5 key entities, 7 success criteria, explicit scope/assumptions/dependencies sections. One NEEDS CLARIFICATION remains in FR-013: dashboard network accessibility (localhost-only vs. local-network). All other checklist items pass.

## Outcome

- ✅ Impact: Spec created for the OpenClaw MCP gateway + dashboard rebuild. Covers the `openclaw gateway status` and `openclaw doctor` CLI commands, the locally hosted dashboard with run-now trigger, and the Claude Code independence gate.
- 🧪 Tests: No code tests at spec stage
- 📁 Files: specs/005-mcp-dashboard/spec.md, specs/005-mcp-dashboard/checklists/requirements.md
- 🔁 Next prompts: Answer FR-013 clarification (localhost vs network), then `/sp.plan`
- 🧠 Reflection: The "Option B rebuild" framing aligns with the constitution's Technology Stack table which already describes "OpenClaw (Node.js agent gateway)" as the canonical orchestrator — this feature implements what the constitution intended. The Claude Code independence gate (User Story 5 / FR-008) is unusual in that it's a negative requirement (absence of a reference), but it maps cleanly to an automated grep audit as the acceptance test.

## Evaluation notes (flywheel)

- Failure modes observed: null
- Graders run and results (PASS/FAIL): Checklist — 1 NEEDS CLARIFICATION pending
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Resolve FR-013 then run spec-scorer to confirm ≥9.5/10 before planning
