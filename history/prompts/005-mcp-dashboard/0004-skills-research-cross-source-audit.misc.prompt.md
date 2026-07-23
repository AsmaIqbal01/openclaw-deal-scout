---
id: "0004"
title: Skills Research Cross-Source Audit
stage: misc
date: 2026-07-23
surface: agent
model: claude-sonnet-4-6
feature: 005-mcp-dashboard
branch: 005-mcp-dashboard
user: AsmaIqbal01
command: skills research — github.com/openclaw/openclaw + clawhub.ai + skills.sh broad search
labels: ["misc","skills","mcp","fastmcp","research","pre-implementation"]
links:
  spec: specs/005-mcp-dashboard/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - null
tests:
  - null
---

## Prompt

Before we install anything, also check:
1. https://github.com/openclaw/openclaw - any built-in skills or agents relevant to this project
2. https://clawhub.ai - OpenClaw-curated skills directory
Search both against our project context (MCP gateway, deal detection pipeline, Python FastMCP) and tell me if anything relevant exists there that skills.sh missed. Then give me a final combined list before I approve any installs.

[Follow-up mid-turn]: Use find-skills to do a broader search on skills.sh for these specific topics relevant to our project:
1. MCP server
2. Python FastMCP
3. API integration
4. deal detection
5. pipeline orchestration
List everything relevant that comes back. Don't install anything yet.

## Response snapshot

Checked three sources:

**github.com/openclaw/openclaw**: Found `skills/` directory with ~45 built-in skills. Relevant finds: (1) `mcporter` — CLI tool for calling and inspecting MCP tools over HTTP (`mcporter call <server.tool>`); acts as a live smoke-test harness for the 6 MCP tools without a Python client. (2) `healthcheck` — runs `openclaw gateway status --deep` and `openclaw doctor`; useful reference for FR-016 `doctor` subcommand output format. (3) `gemini` — Gemini CLI wrapper, not relevant (we use the Python API, not CLI).

**clawhub.ai**: Primarily Node.js plugins. Nothing matching MCP Python building, FastMCP, or deal detection pipeline work.

**Broader skills.sh searches** (5 topics): Key finds beyond previous searches:
- `github/awesome-copilot@python-mcp-server-generator` (10K installs) — Python MCP server code gen, high-trust GitHub org source
- `jlowin/fastmcp@testing-python` (88 installs) — FastMCP creator's own testing skill from the `jlowin/fastmcp` library repo; most authoritative source for FastMCP pytest fixture patterns
- `onewave-ai/claude-skills@gmail-to-crm-pipeline` (155 installs) — named after our exact use case (Gmail → CRM pipeline); workflow-level, not implementation-level

**Updated shortlist (7 candidates):**
1. `anthropics/skills@mcp-builder` (92.8K) — MCP tool schema + contract alignment
2. `anthropics/skills@webapp-testing` (119.8K) — HTTP server E2E/CLI testing
3. `jlowin/fastmcp@testing-python` (88) — FastMCP creator's own pytest patterns; replaces generic pytest skill
4. `github/awesome-copilot@python-mcp-server-generator` (10K) — Python MCP codegen
5. `openclaw/openclaw@mcporter` (built-in) — live HTTP smoke-test harness
6. `openclaw/openclaw@healthcheck` (built-in) — `doctor` command reference
7. `onewave-ai/claude-skills@gmail-to-crm-pipeline` (155) — workflow-level pipeline reference

Install priority (pending approval): mcp-builder → jlowin/fastmcp@testing-python → mcporter (built-in) → webapp-testing

## Outcome

- ✅ Impact: Identified 2 built-in openclaw skills missed by skills.sh (mcporter, healthcheck); identified jlowin/fastmcp@testing-python as the highest-authority FastMCP testing source. Clawhub.ai confirmed no relevant Python/MCP skills.
- 🧪 Tests: null
- 📁 Files: null (research only)
- 🔁 Next prompts: approve skill installs → /sp.tasks
- 🧠 Reflection: jlowin/fastmcp@testing-python is the most valuable find — low install count but the FastMCP library creator's own skill is the ground truth for FastMCP pytest fixture teardown. The mcporter built-in skill eliminates the need to write a Python MCP client for smoke tests.

## Evaluation notes (flywheel)

- Failure modes observed: clawhub.ai page was truncated/placeholder-heavy — second WebFetch prompt needed to confirm nothing was hidden
- Graders run and results (PASS/FAIL): Source coverage — 3 sources checked PASS; relevance filter applied PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Approve installs → /sp.tasks to generate T001–T0XX
