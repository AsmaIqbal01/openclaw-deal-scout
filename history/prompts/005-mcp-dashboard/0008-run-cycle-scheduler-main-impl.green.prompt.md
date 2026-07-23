---
id: "0008"
title: Run Cycle Scheduler Main Implementation
stage: green
date: 2026-07-24
surface: agent
model: claude-sonnet-4-6
feature: 005-mcp-dashboard
branch: 005-mcp-dashboard
user: AsmaIqbal01
command: implement T024 through T029
labels: ["green","mcp","scheduler","run_cycle","main","threading"]
links:
  spec: specs/005-mcp-dashboard/spec.md
  ticket: "null"
  adr: history/adr/0005-gateway-scheduler-architecture.md
  pr: "null"
files:
  - tests/unit/test_gateway_scheduler.py          # created: 4 SchedulerThread tests
  - tests/unit/test_gateway_tools_pipeline.py      # extended: TestRunCycle (6 tests)
  - tests/integration/test_gateway_e2e.py          # created: 4 E2E tests (skipped by default)
  - src/openclaw_gateway/tools/pipeline.py         # extended: real run_cycle() implementation
  - src/openclaw_gateway/scheduler.py              # created: SchedulerThread
  - src/openclaw_gateway/__main__.py               # created: gateway entry point
tests:
  - tests/unit/test_gateway_scheduler.py (4 tests)
  - tests/unit/test_gateway_tools_pipeline.py::TestRunCycle (6 tests)
---

## Prompt

implement T024 through T029

## Response snapshot

Implemented 6 files covering Phase 7 (US4 — manual pipeline trigger + full gateway server):

- **T024**: Created `tests/unit/test_gateway_scheduler.py` (4 tests). Tests: daemon flag, start+stop clean, run_cycle called ≥1 in 0.2s with 0.01s interval, stop exits loop without additional cycles. Uses monkeypatch on `scheduler_mod._run_one_cycle`.

- **T025**: Extended `tests/unit/test_gateway_tools_pipeline.py` with `TestRunCycle` (6 tests). Uses `_make_pipeline_config(tmp_path)` to provide real PipelineConfig so `_CapturingLogger` can write to disk. Patches `pipeline_orchestrator.runner.run_cycle`. Tests: busy dict, message contains "progress"/"running", 6-field PipelineCycle dict, `_cycle_running` cleared, `_last_cycle_at` set.

- **T026**: Created `tests/integration/test_gateway_e2e.py` (4 tests, all skipped by default via `pytestmark = pytest.mark.skip`). Tests: gateway_status returns running, run_cycle returns PipelineCycle, get_pipeline_cycles returns structure, SIGTERM shuts down cleanly within 5s.

- **T027**: Extended `tools/pipeline.py` with real `run_cycle()`. Uses inner `_CapturingLogger(CycleLogger)` that captures the emitted summary dict. Lazy-imports `pipeline_orchestrator.runner` and catches `CycleLockActiveError` → busy dict. `finally: _srv._cycle_running = False` ensures cleanup.

- **T028**: Created `src/openclaw_gateway/scheduler.py`. `SchedulerThread` is `daemon=True`, uses `threading.Event._stop_event.wait(interval)` for interruptible sleep. `_run_one_cycle()` is a module-level function so tests can monkeypatch it. `stop()` sets the event.

- **T029**: Created `src/openclaw_gateway/__main__.py`. Loads `GatewayConfig`, creates `SchedulerThread` if `scheduler_mode == "gateway"`, registers SIGTERM handler, sets `server._gateway_start_time` and `server._config`, calls `server.mcp.run(transport="http", ...)`.

279/279 unit tests pass.

## Outcome

- ✅ Impact: All 6 MCP tools now implemented; full gateway server operational with scheduler and manual trigger
- 🧪 Tests: 279/279 pass (10 new for T024+T025; E2E skipped; existing 269 unaffected)
- 📁 Files: 6 files created/extended
- 🔁 Next prompts: Phase 8 polish — T030 (deploy), T031 (independence check), T032 (full unit sweep), T033 (integration test)
- 🧠 Reflection: inner class `_CapturingLogger` captures summary without needing to re-read the log file; `_run_one_cycle` module-level function enables clean monkeypatching without complex DI

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): self-review PASS; 279/279 pytest PASS
- Prompt variant (if applicable): none
- Next experiment: T030–T033 Phase 8 polish
