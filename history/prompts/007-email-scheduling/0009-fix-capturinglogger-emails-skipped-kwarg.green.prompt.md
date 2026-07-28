---
id: 0009
title: Fix CapturingLogger emails_skipped kwarg crash
stage: green
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: 007-email-scheduling
branch: main
user: AsmaIqbal01
command: none
labels: ["bugfix", "gateway", "run_cycle", "cycle_logger"]
links:
  spec: specs/007-email-scheduling/spec.md
  ticket: null
  adr: null
  pr: null
---

## Prompt

Fix this error that occurred during run_cycle via the gateway:"run_cycle.<locals>._CapturingLogger.emit_cycle_summary() got an unexpected keyword argument 'emails_skipped'"The gateway's run_cycle route has an internal _CapturingLogger that wraps emit_cycle_summary but doesn't accept the new email keyword args added in 007. Fix it to accept **kwargs or add the missing email fields.

## Response snapshot

Located `_CapturingLogger` in `src/openclaw_gateway/tools/pipeline.py:20-27` (the `run_cycle` MCP tool). Its `emit_cycle_summary` override hardcoded the pre-007 keyword set (`emails_scheduled`, `emails_dispatched`), so it broke as soon as `CycleLogger.emit_cycle_summary` (src/pipeline_orchestrator/cycle_logger.py:29-41) gained `emails_skipped` and `emails_failed` in 007. Replaced the hardcoded params with `**kwargs`, forwarded to both `super().emit_cycle_summary(...)` and the `captured.update(...)` call, so any current or future `CycleLogger` fields pass through without further edits to this wrapper. Ran the gateway pipeline test suites to confirm the fix, then committed (`8ccbc0e`) and pushed directly to `origin/main` at the user's request.

## Outcome

- ✅ Impact: `run_cycle` no longer raises `TypeError` on `emails_skipped`/`emails_failed`; `_CapturingLogger` now future-proof against new `CycleLogger` kwargs.
- 🧪 Tests: `tests/unit/test_gateway_tools_pipeline.py` (18 passed); `tests/unit/test_gateway_scheduler.py`, `tests/integration/test_gateway_e2e.py`, `tests/integration/test_full_pipeline.py` (19 passed, 4 skipped).
- 📁 Files: src/openclaw_gateway/tools/pipeline.py
- 🔁 Next prompts: none pending; fix is committed and pushed.
- 🧠 Reflection: Wrapper subclasses that re-declare a base method's keyword args are a recurring drift risk — prefer `**kwargs` passthrough for thin logging/capturing wrappers so upstream signature growth doesn't require synchronized edits.

## Evaluation notes (flywheel)

- Failure modes observed: Hardcoded keyword allowlist in a subclass silently went stale when the base class gained new optional kwargs in a later feature (007).
- Graders run and results (PASS/FAIL): pytest — PASS (37 relevant tests green).
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
