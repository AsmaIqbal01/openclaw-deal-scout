---
id: "002"
title: Spec Scorer Subagent Creation
stage: general
date: 2026-07-09
surface: agent
model: claude-sonnet-4-6
feature: none
branch: master
user: AsmaIqbal000
command: inline prompt
labels: ["subagent","spec-quality","rubric","spec-scorer","tooling"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - .claude/agents/spec-scorer.md
tests:
  - null
---

## Prompt

Create a new Claude Code subagent file at `.claude/agents/spec-scorer.md`.

CONTEXT:
This is for the "OpenClaw Deal Scout" project, which builds specs using the
Panaversity SpecifyPlus workflow (/sp.specify, /sp.plan, /sp.tasks). Specs are
written for 4 independent steps (Gmail Intake, HubSpot CRM Logging, Discord
Notification, Orchestration & Error Handling). Every spec must be scored
against a fixed rubric before moving to /sp.plan, and revised in a loop until
it averages 9.5/10 or higher.

PURPOSE OF THIS SUBAGENT:
Given a spec document (markdown, following .specify/templates/spec-template.md),
score it against the 7-criterion rubric below, output a score table, identify
the single LOWEST-scoring criterion, and suggest a specific, actionable revision
for that criterion only (not the whole spec). This subagent is reused across all
4 steps of the project — it must not hardcode any step-specific content.

RUBRIC (score each 1-10):
1. Clarity of scope — no leakage between this step and other steps in the pipeline
2. Testability — every functional requirement (FR) has a verifiable success condition
3. Constitution alignment — references relevant constitution principles, passes
   all 6 Constitution Check Gates (read from .specify/memory/constitution.md)
4. Completeness — edge cases covered (empty inbox, malformed input, duplicate ID,
   rate limits, etc., as relevant to the step)
5. Interface precision — I/O contracts (e.g. DealPayload) are concretely typed,
   not vague prose
6. Error path coverage — exact failure behavior specified per failure mode, not
   just the happy path
7. No unresolved ambiguity — zero [NEEDS CLARIFICATION] markers left in the spec

BEHAVIOR REQUIRED:
- Read the constitution file at .specify/memory/constitution.md to ground the
  "Constitution alignment" criterion in the actual 6 principles/gates, not a
  generic guess.
- Output format: a markdown table (Criterion | Score | Why), followed by:
  - Overall average score
  - PASS (≥9.5) or REVISE (<9.5) verdict
  - If REVISE: name the single lowest-scoring criterion and give a concrete,
    targeted rewrite suggestion (specific sentences/sections to add or change) —
    do not suggest revising multiple criteria at once
- Be strict, not encouraging — the rubric exists to catch real gaps before
  /sp.plan burns time on an ambiguous spec. Deduct points for vague language,
  unstated assumptions, or missing failure modes.
- Do not modify the spec file directly — only output the score table and
  suggestion as a response, so the human can decide whether to accept it.

Write this as a proper Claude Code subagent file with YAML frontmatter
(name, description, tools if needed) followed by the system prompt / instructions
for the subagent. Keep it generic and reusable — do not reference "Gmail" or
"HubSpot" or "Discord" by name anywhere in the file.

## Response snapshot

Created `.claude/agents/spec-scorer.md` as a reusable Claude Code subagent with:
- YAML frontmatter: name, description, tools (Read, Glob, Grep — read-only, no
  write tools to enforce the no-modify-spec constraint)
- Step 1: reads `.specify/memory/constitution.md` before scoring to ground
  Criterion 3 in actual project principles and the 6 Constitution Check Gates
- Step 2: 7-criterion rubric table with per-criterion "what to check" guidance
- Step 3: fixed output format — score table → average → PASS/REVISE verdict →
  single revision target (only when REVISE)
- Hard constraints: read-only, one criterion per revision cycle, strict scoring,
  error messages for missing inputs

## Outcome

- ✅ Impact: Project now has a reusable gating tool that enforces spec quality
  before every /sp.plan invocation across all 4 pipeline steps.
- 🧪 Tests: N/A (subagent definition file; tested by invocation against a real spec)
- 📁 Files: .claude/agents/spec-scorer.md
- 🔁 Next prompts: invoke the scorer against the first spec written with /sp.specify
- 🧠 Reflection: No step-specific names appear in the subagent file; constitution
  is always loaded fresh at runtime so scores stay grounded in the current
  constitution version.

## Evaluation notes (flywheel)

- Failure modes observed: none at authoring time
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): initial authoring
- Next experiment: score a real spec and verify the rubric catches interface
  precision gaps (Criterion 5) which are historically under-specified
