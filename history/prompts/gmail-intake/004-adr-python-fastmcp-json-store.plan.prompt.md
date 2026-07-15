---
id: "004"
title: ADR Python FastMCP and JSON Store
stage: plan
date: 2026-07-09
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: /sp.adr python-fastmcp-subprocess
labels: ["adr","architecture","fastmcp","python","state-store","json","sqlite","stdio"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: history/adr/0001-python-fastmcp-subprocess-runtime.md
  pr: null
files:
  - history/adr/0001-python-fastmcp-subprocess-runtime.md
  - history/adr/0002-json-file-state-store-mechanism.md
tests:
  - null
---

## Prompt

/sp.adr python-fastmcp-subprocess

## Response snapshot

Created 2 ADRs documenting architecturally significant decisions from the gmail-intake plan:

**ADR-0001: Python FastMCP Subprocess Runtime**
- Decision cluster: Python 3.11+ / fastmcp / stdio transport / subprocess process model
- 3 alternatives considered: TypeScript MCP server, Python child_process (outside MCP), HTTP/SSE transport
- Key rejection reason for TypeScript: google-generativeai JS SDK lacks response_schema structured-output support as of 2026-Q2
- Key rejection reason for HTTP/SSE: over-engineered for a polling tool invoked every few minutes; adds daemon management complexity
- Significance test: PASS on all 3 — long-term cross-language commitment, multiple viable alternatives, cross-cutting (affects all future pipeline tools)

**ADR-0002: JSON File State Store Mechanism**
- Decision cluster: flat JSON file / portalocker LOCK_EX|LOCK_NB / tempfile+os.rename atomic writes / 50 MB warn threshold
- 4 alternatives considered: SQLite, in-memory dict, Redis, append-only log file
- Key rejection: SQLite rejected for MVP (human-readability and re-processing ergonomics outweigh query capability at current volume); Redis rejected for zero-cost constraint; in-memory explicitly prohibited by Constitution Principle IV
- Significance test: PASS on all 3 — affects all future pipeline steps, multiple viable alternatives, schema + locking strategy are cross-cutting

No existing ADRs conflicted (history/adr/ was empty before this command).

## Outcome

- ✅ Impact: Two ADRs documenting the two most consequential architectural decisions in the gmail-intake plan; both are cross-cutting and will govern future HubSpot and Discord pipeline steps.
- 🧪 Tests: N/A (architecture documents)
- 📁 Files: history/adr/0001-python-fastmcp-subprocess-runtime.md, history/adr/0002-json-file-state-store-mechanism.md
- 🔁 Next prompts: /sp.tasks to generate implementation tasks; git checkpoint to commit ADRs
- 🧠 Reflection: ADR-0002 was created proactively (not in the user's argument) because it meets all three significance tests and was flagged during /sp.plan. Grouping it here avoids a separate /sp.adr session for a tightly coupled decision.

## Evaluation notes (flywheel)

- Failure modes observed: create-adr.sh required --title flag (positional args not supported); fixed by using --title flag explicitly
- Graders run and results (PASS/FAIL): significance test — both ADRs PASS all 3 criteria
- Prompt variant (if applicable): user specified python-fastmcp-subprocess; JSON state store added proactively
- Next experiment: after /sp.tasks, check whether the task list references these ADRs correctly in task descriptions
