---
id: "0005"
title: MCP Gateway Task List Generated
stage: tasks
date: 2026-07-23
surface: agent
model: claude-sonnet-4-6
feature: 005-mcp-dashboard
branch: 005-mcp-dashboard
user: AsmaIqbal01
command: /sp.tasks
labels: ["tasks","mcp","fastmcp","gateway","scheduler","cli","python","tdd"]
links:
  spec: specs/005-mcp-dashboard/spec.md
  ticket: null
  adr: history/adr/0005-gateway-scheduler-architecture-single-process-thread-model.md
  pr: null
files:
  - specs/005-mcp-dashboard/tasks.md
tests:
  - null
---

## Prompt

Install A, B, C, D in one pass then /sp.tasks

[Context: A = anthropics/skills@mcp-builder, B = jlowin/fastmcp@testing-python, C = openclaw/openclaw@mcporter, D = anthropics/skills@webapp-testing. Branch: 005-mcp-dashboard. ADR-0004 and ADR-0005 complete. All design docs available: spec.md, plan.md, data-model.md, contracts/mcp-tools.md]

## Response snapshot

Generated `specs/005-mcp-dashboard/tasks.md` with 33 tasks across 8 phases:

- **Phase 1 (Setup, T001–T005)**: Package directories, `__init__.py`, `pyproject.toml` entry-point, dependency pins
- **Phase 2 (Foundational, T006–T007)**: `GatewayConfig` dataclass + `load_gateway_config()` + unit tests — blocks all user story phases
- **Phase 3 (US5/P1, T008)**: `test_claude_code_independence.py` — stdlib grep of `src/` for `claude|anthropic` patterns; 0 matches required
- **Phase 4 (US1/P1, T009–T012)**: `get_health()` + `openclaw doctor` subcommand; TDD — 2 test tasks [P] then 2 impl tasks
- **Phase 5 (US2/P2, T013–T017)**: `FastMCP("openclaw-gateway")` server.py + `get_gateway_status()` + `openclaw gateway status` / `dashboard` CLI
- **Phase 6 (US3/P3, T018–T023)**: `readers.py` (read_pipeline_log, read_deals, compute_quota_usage) + 3 pipeline read tools; 2 test tasks [P] + 4 impl tasks (2 [P])
- **Phase 7 (US4/P4, T024–T029)**: `run_cycle()` with portalocker, `SchedulerThread`, `__main__.py` entry-point; 3 test tasks + 3 impl tasks; T026 = E2E integration test
- **Phase 8 (Polish, T030–T033)**: systemd deploy update, independence gate re-run, unit suite, integration suite

Source files mapped: `config.py`, `readers.py`, `tools/status.py`, `tools/pipeline.py`, `server.py`, `scheduler.py`, `__main__.py`, `cli.py` (8 modules). Test files: `test_gateway_config.py`, `test_claude_code_independence.py`, `test_gateway_tools_status.py`, `test_gateway_cli.py`, `test_gateway_readers.py`, `test_gateway_tools_pipeline.py`, `test_gateway_scheduler.py`, `test_gateway_e2e.py` (8 test files).

## Outcome

- ✅ Impact: 33 executable tasks fully mapped to spec/plan/data-model/contracts; each user story independently testable; MVP scope clearly bounded (US5+US1 = 7 tasks to a shippable increment)
- 🧪 Tests: 8 test files scaffolded as tasks — TDD: test tasks always precede impl tasks within each phase
- 📁 Files: specs/005-mcp-dashboard/tasks.md
- 🔁 Next prompts: implement T001–T008 (setup + foundational + independence gate), then T009–T012 (US1 doctor MVP)
- 🧠 Reflection: Phase ordering matters here — US5 independence test (T008) must be written before any src/ modules exist so it starts green by default, then stays green as code grows. Placing it before US1 in Phase 3 enforces this. The shared `tools/status.py` (US1 + US2) and `tools/pipeline.py` (US3 + US4) both accumulate across phases — the notes section explicitly warns about file-conflict coordination.

## Evaluation notes (flywheel)

- Failure modes observed: openclaw/openclaw@mcporter skill install (background task bao0htsi5) failed with exit code 1 — large repo (~210MB JS/TS); anthropics/skills@webapp-testing (bi2xvaaky) also failed exit 1. Both skills B (jlowin/fastmcp@testing-python) and A (anthropics/skills@mcp-builder) confirmed installed successfully.
- Graders run and results (PASS/FAIL): Task count per user story — PASS (US5:1, US1:4, US2:5, US3:6, US4:6); TDD ordering — PASS (tests before impl in every phase); no placeholder text in tasks.md — PASS; all file paths match plan.md layout — PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Retry mcporter + webapp-testing installs separately with --timeout flag, then begin T001 implementation
