---
id: "0003"
title: ADR Browser Gateway REST Adapter
stage: misc
date: 2026-07-24
surface: agent
model: claude-sonnet-4-6
feature: 006-web-dashboard
branch: 006-web-dashboard
user: AsmaIqbal01
command: /sp.adr browser-to-gateway-rest-adapter
labels: ["adr","architecture","rest","fastmcp","browser","dashboard"]
links:
  spec: specs/006-web-dashboard/spec.md
  ticket: "null"
  adr: history/adr/0006-browser-to-gateway-rest-adapter-pattern.md
  pr: "null"
files:
  - history/adr/0006-browser-to-gateway-rest-adapter-pattern.md
tests:
  - "null"
---

## Prompt

/sp.adr browser-to-gateway-rest-adapter

## Response snapshot

Created ADR-0006: Browser-to-Gateway REST Adapter Pattern.

**Decision**: Add five thin REST endpoints (`/api/*`) to the existing FastMCP gateway via `@mcp.custom_route()`. Browser uses plain `fetch()` — no MCP protocol knowledge required. REST handlers delegate to the same implementation functions as MCP tools (zero logic duplication).

**Significance test**: PASS on all three gates — cross-cutting impact, multiple alternatives considered, will be revisited if real-time push becomes a requirement.

**Alternatives evaluated**: Direct MCP session from browser (rejected — brittle session handshake), WebSockets (deferred — no push events today), separate HTTP server on second port (rejected — violates zero-new-processes constraint), SSE auto-push (deferred — polling sufficient for 60s interval).

**Existing ADRs checked**: 0001–0005, none conflict with or cover this decision. ADR-0004 (gateway HTTP transport) and ADR-0005 (scheduler architecture) referenced as related context.

## Outcome

- ✅ Impact: REST adapter pattern documented as accepted; unblocks /sp.tasks and implementation
- 🧪 Tests: None at ADR stage
- 📁 Files: 1 file written (history/adr/0006-browser-to-gateway-rest-adapter-pattern.md)
- 🔁 Next prompts: `/sp.adr dashboard-zero-build-single-file` (second ADR candidate) or `/sp.tasks` to generate task list
- 🧠 Reflection: Decision was already well-documented in research.md (Decision 2); ADR adds the formal architectural framing, significance test, and consequences that make it referenceable in future planning

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): Significance test PASS (3/3 gates); ADR checklist PASS (clustered decision, alternatives listed, pros/cons documented, references linked)
- Prompt variant (if applicable): "null"
- Next experiment: "null"
