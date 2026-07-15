---
id: "003"
title: Gmail Intake Implementation Plan
stage: plan
date: 2026-07-09
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: /sp.plan
labels: ["plan","gmail-intake","fastmcp","python","gemini","state-store","oauth","architecture"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/001-gmail-intake/plan.md
  - specs/001-gmail-intake/research.md
  - specs/001-gmail-intake/data-model.md
  - specs/001-gmail-intake/contracts/tool-contract.md
  - specs/001-gmail-intake/quickstart.md
tests:
  - tests/unit/test_classifier.py (planned)
  - tests/unit/test_extractor.py (planned)
  - tests/unit/test_state_store.py (planned)
  - tests/integration/test_check_new_deals.py (planned)
  - tests/contract/test_tool_contract.py (planned)
---

## Prompt

/sp.plan

(No additional arguments — plan context derived from spec at specs/001-gmail-intake/spec.md
and constitution at .specify/memory/constitution.md)

## Response snapshot

Generated complete implementation plan for the Gmail Intake & Deal Detection feature.

**Architecture selected**: Python 3.11+ FastMCP server (separate process from OpenClaw
Node.js gateway) connected via stdio MCP transport.

**Phase 0 research resolved**:
- Language: Python (FastMCP is Python-native; google-generativeai Python SDK has
  structured-output support)
- Transport: stdio (zero network config; OpenClaw spawns Python server as subprocess)
- File lock: portalocker LOCK_EX|LOCK_NB for FR-003b concurrent invocation detection
- Atomic writes: tempfile + os.rename() POSIX atomic for FR-013 crash recovery
- Gemini JSON mode: response_mime_type="application/json" + response_schema (no manual JSON parsing)
- FR-011 sentence boundary: regex with title-abbreviation exclusion list (Dr., Mr.,
  Mrs., acronyms, initials); resolves the spec-scorer round 11 ambiguity
- Classifier prompt: versioned in research.md as prompt v1.0 (FR-006 requirement)

**Phase 1 artifacts produced**:
1. plan.md — Technical context, constitution check (5 PASS, 1 N/A), module
   responsibilities, error handling matrix (15 failure scenarios)
2. research.md — 10 decisions with rationale, exact Python code snippets for all
   key implementation patterns, classifier prompt v1.0 (verbatim), FR-011 regex
3. data-model.md — 5 Python dataclasses (DealPayload, ProcessedMessage,
   ClassificationRequest, ClassificationResponse, StateStore) with field-level
   validation rules, outcome enum semantics, entity relationship diagram
4. contracts/tool-contract.md — MCP tool interface, 3 JSON wire format examples,
   count semantics identity, error detail taxonomy, versioning policy
5. quickstart.md — 7-step setup guide from prerequisites to first run; common
   issues table; gitignore verification

**Constitution check**: ✅ 5 PASS, 1 N/A — cleared for implementation

**Agent context updated**: CLAUDE.md updated with Python 3.11+ and JSON state store technology.

**ADR triggers identified**: 2 architecturally significant decisions flagged for operator review.

## Outcome

- ✅ Impact: Full implementation plan for gmail-intake complete; all NEEDS CLARIFICATION
  resolved; 5 plan artifacts written; classifier prompt v1.0 versioned; FR-011 sentence
  boundary fully specified; constitution gates pass.
- 🧪 Tests: Test file structure planned (5 test files); test cases for FR-011 regex
  defined in research.md
- 📁 Files: plan.md, research.md, data-model.md, contracts/tool-contract.md, quickstart.md
- 🔁 Next prompts: /sp.tasks to generate implementation tasks with TDD red-green-refactor
  cycles; then git checkpoint for plan artifacts
- 🧠 Reflection: The FR-011 ambiguity (title abbreviations) from the spec-scorer was
  fully resolved at the plan level with a concrete regex implementation — this is the
  right place to resolve it since it's an implementation detail, not a spec gap.
  The Python-vs-TypeScript decision for FastMCP was the most significant architectural
  choice; it was driven by structured-output support quality in the Gemini SDK.

## Evaluation notes (flywheel)

- Failure modes observed: none — spec was complete enough that planning was
  straightforward; all decisions followed directly from the spec's constraints
- Graders run and results (PASS/FAIL): constitution gate check — 5 PASS, 1 N/A
- Prompt variant (if applicable): standard /sp.plan command with no extra args
- Next experiment: run spec-scorer-style review against plan.md after /sp.tasks to
  validate plan quality before implementation begins
