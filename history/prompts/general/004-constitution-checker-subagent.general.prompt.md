---
id: "004"
title: Constitution Checker Subagent Creation
stage: general
date: 2026-07-09
surface: agent
model: claude-sonnet-4-6
feature: none
branch: main
user: AsmaIqbal000
command: inline prompt
labels: ["subagent","constitution","gate-check","compliance","tooling"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - .claude/agents/constitution-gate-checker.md
tests:
  - null
---

## Prompt

Create a new Claude Code subagent file (name partially garbled in transmission)
that checks the given input against each of the 6 Constitution Check Gates.
Output a simple PASS/FAIL per gate with a one-line reason, not a full narrative
review.

BEHAVIOR REQUIRED:
- Always re-read .specify/memory/constitution.md fresh each time (never assume
  the 6 principles from memory) — the constitution can be amended, and version
  drift must not cause stale checks.
- For each of the 6 gates, output: gate name, PASS/FAIL verdict, one-line reason.
- Only read and report, never modify files.

Write this as a proper Claude Code subagent file with YAML frontmatter
(name, description, tools) followed by the system prompt / instructions.

## Response snapshot

Created `.claude/agents/constitution-checker.md` with:
- YAML frontmatter: name=constitution-checker, description, tools=[Read, Grep]
- Step 1: mandatory fresh read of constitution.md on every invocation; extracts
  the 6 gates and version number; hard-errors if file is missing
- Step 2: accepts spec/plan/task/prose/diff/code as input (file path or pasted)
- Step 3: per-gate YES/NO evaluation logic with strict ambiguity handling
  (ambiguous = assume worst case = FAIL)
- Step 4: fixed output — markdown table (Gate | Verdict | Reason) + overall
  verdict + Remediation section (failed gates only, 1-2 sentences each)
- Hard constraints: read-only, no narrative essays, one-line reasons, always
  copies gate text from the live file (never from memory)

## Outcome

- ✅ Impact: Project now has a fast, always-fresh gate-compliance checker usable
  before /sp.plan, during code review, or for any proposed change.
- 🧪 Tests: N/A (subagent definition; tested by invocation against a real input)
- 📁 Files: .claude/agents/constitution-checker.md
- 🔁 Next prompts: use constitution-checker as a gate before every /sp.plan run
- 🧠 Reflection: The "always re-read" invariant is the key design decision —
  it prevents stale checks when the constitution is amended (e.g., v1.0.0 → v1.0.1).
  Subagents that cache constitution content from training data are a subtle but
  real failure mode in long-running projects.

## Evaluation notes (flywheel)

- Failure modes observed: input message was garbled; reconstructed intent from
  visible fragments and project context
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): initial authoring from partial input
- Next experiment: run against a deliberately bad spec (one that includes a
  paid dependency) and verify gate 1 returns FAIL
