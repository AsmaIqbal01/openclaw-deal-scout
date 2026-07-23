# Tasks: OpenClaw MCP Gateway + Dashboard (005-mcp-dashboard)

**Input**: `specs/005-mcp-dashboard/` — plan.md, spec.md, data-model.md, contracts/mcp-tools.md
**Branch**: `005-mcp-dashboard`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package scaffold and dependency wiring — no business logic yet.

- [ ] T001 Create `src/openclaw_gateway/` and `src/openclaw_gateway/tools/` directories (empty `__init__.py` files as placeholders)
- [ ] T002 Create `src/openclaw_gateway/__init__.py` with `__version__ = "0.1.0"` and package docstring
- [ ] T003 [P] Create `src/openclaw_gateway/tools/__init__.py` (empty)
- [ ] T004 Add `openclaw = "openclaw_gateway.cli:main"` entry-point under `[project.scripts]` in `pyproject.toml`
- [ ] T005 [P] Add `fastmcp>=2.0` (pin comment: tested at 3.4.4) and `portalocker>=2.8` to `[project.dependencies]` in `pyproject.toml`; run `pip install -e .` to verify install

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `GatewayConfig` is the single shared config object consumed by every module. Nothing else can be built until it exists.

**⚠️ CRITICAL**: All user story phases depend on this phase being complete first.

- [ ] T006 Implement `GatewayConfig` dataclass and `load_gateway_config()` in `src/openclaw_gateway/config.py` — 10 fields including `gateway_host` (env `GATEWAY_HOST`, default `"127.0.0.1"`), `gateway_port` (env `GATEWAY_PORT`, default `18789`, cast to int), `scheduler_mode` (env `SCHEDULER_MODE`, default `"cron"`, extended with `"gateway"` value); all other fields inherited from `OrchestratorConfig`
- [ ] T007 [P] Write `tests/unit/test_gateway_config.py` — verify: defaults when no env vars set, `GATEWAY_HOST`/`GATEWAY_PORT`/`SCHEDULER_MODE` override via monkeypatch, `gateway_port` coerced to int, `scheduler_mode="gateway"` accepted

**Checkpoint**: GatewayConfig verified → all user story phases can begin.

---

## Phase 3: User Story 5 — Claude Code Independence Gate (Priority: P1) 🎯

**Goal**: Production `src/` must contain zero references to `claude`, `anthropic`, or any developer-tooling identifiers — permanently enforced as a pytest test that runs in every CI pass.

**Independent Test**: `pytest tests/unit/test_claude_code_independence.py` → 0 matches, exit 0.

- [ ] T008 [US5] Write `tests/unit/test_claude_code_independence.py` — uses `pathlib.Path("src").rglob("*.py")` + `re.search(r"claude|anthropic", line, re.IGNORECASE)` to grep every `.py` file under `src/`; `assert matches == []` with a detailed failure message listing each flagged file+line; must run with no import of `openclaw_gateway` (pure stdlib + pathlib)

**Checkpoint**: Independence gate live — any accidental dev-tooling import will now be caught immediately.

---

## Phase 4: User Story 1 — Instant Health Check via `openclaw doctor` (Priority: P1) 🎯 MVP

**Goal**: `openclaw doctor` prints a per-component health table and exits 0 (all healthy) or 1 (any degraded).

**Independent Test**: `openclaw doctor` — prints table with `state_store`, `pipeline_log`, `network` rows; exit code is 0 when files exist and reachable.

### Tests for US1 (write first — must FAIL before implementation)

- [ ] T009 [P] [US1] Write `tests/unit/test_gateway_tools_status.py` (get_health section) — test: all-pass path returns `HealthCheckReport` with `overall="healthy"` and 3 components each `status="ok"`; test: `state_store` fail path (file missing) → `overall="degraded"`, `status="error"` for that component; test: each component dict has keys `name`, `status`, `latency_ms`, `message`
- [ ] T010 [P] [US1] Write `tests/unit/test_gateway_cli.py` (doctor section) — mock `get_health()` return; test: stdout contains component name + status columns; test: exit 0 when `overall=="healthy"`; test: exit 1 when `overall=="degraded"`

### Implementation for US1

- [ ] T011 [US1] Implement `get_health()` in `src/openclaw_gateway/tools/status.py` — returns `HealthCheckReport` dict; 3 components: (1) `state_store` — check `Path(config.state_store_path).is_file()`; (2) `pipeline_log` — check `Path(config.pipeline_log_path).exists()`; (3) `network` — `socket.create_connection((config.gateway_host, config.gateway_port), timeout=1)` (reports `"unreachable"` as warning, not error, since gateway may not be running during doctor check); record `latency_ms` for each; `overall = "healthy"` if all status `!= "error"` else `"degraded"`; `checked_at = datetime.utcnow().isoformat()`, `duration_ms` = total wall time
- [ ] T012 [US1] Implement `openclaw doctor` subcommand in `src/openclaw_gateway/cli.py` — argparse `subparsers.add_parser("doctor")`; calls `get_health(load_gateway_config())`; prints formatted table: `Component | Status | Latency | Message`; exits `sys.exit(0)` if `overall == "healthy"` else `sys.exit(1)`; stdlib only (`argparse`, `sys`)

**Checkpoint**: `openclaw doctor` works end-to-end; US1 acceptance scenarios pass.

---

## Phase 5: User Story 2 — Gateway Status Check via CLI (Priority: P2)

**Goal**: `openclaw gateway status` shows live uptime + connection info; `openclaw dashboard` opens the MCP inspector in the browser.

**Independent Test**: With gateway running: `openclaw gateway status` → prints running status + uptime; exit 0. With gateway stopped: exit 1. `openclaw dashboard` → `webbrowser.open()` called.

### Tests for US2 (write first — must FAIL before implementation)

- [ ] T013 [P] [US2] Extend `tests/unit/test_gateway_tools_status.py` (get_gateway_status section) — test: returns dict with keys `running`, `uptime_seconds`, `version`, `host`, `port`, `last_cycle_at`, `cycle_running`; test: `version` equals `openclaw_gateway.__version__`; test: `uptime_seconds` is non-negative float; test: `running=True` when server state set
- [ ] T014 [P] [US2] Extend `tests/unit/test_gateway_cli.py` (gateway/dashboard section) — mock HTTP response; test: `gateway status` prints host, port, uptime; test: running gateway → exit 0, connection refused → exit 1; test: `dashboard` calls `webbrowser.open` with URL containing `gateway_host:gateway_port`

### Implementation for US2

- [ ] T015 [US2] Implement `src/openclaw_gateway/server.py` — `mcp = FastMCP("openclaw-gateway")`; module-level state: `_gateway_start_time: float = 0.0`, `_last_cycle_at: Optional[str] = None`, `_cycle_running: bool = False`; import and register all 6 tools with `@mcp.tool()` decorators: `get_gateway_status`, `get_health`, `run_cycle`, `get_pipeline_cycles`, `get_deals`, `get_quota_usage` (tool function bodies live in `tools/status.py` and `tools/pipeline.py` — `server.py` only wires them up)
- [ ] T016 [US2] Implement `get_gateway_status()` in `src/openclaw_gateway/tools/status.py` — reads `server._gateway_start_time` for `uptime_seconds = time.time() - _gateway_start_time`; reads `server._last_cycle_at` and `server._cycle_running`; returns `GatewayStatus` dict: `{"running": True, "uptime_seconds": ..., "version": __version__, "host": config.gateway_host, "port": config.gateway_port, "last_cycle_at": ..., "cycle_running": ...}`
- [ ] T017 [US2] Add `gateway` and `dashboard` subcommands to `src/openclaw_gateway/cli.py` — `gateway status`: HTTP GET to `http://{host}:{port}/mcp/tool/get_gateway_status` with 2 s timeout; on success print running status + uptime; on `ConnectionRefusedError` / timeout print "Gateway not running" + exit 1; `dashboard`: `webbrowser.open(f"http://{config.gateway_host}:{config.gateway_port}")` + print URL to stdout

**Checkpoint**: US1 + US2 both independently functional; `openclaw gateway status` and `openclaw doctor` work.

---

## Phase 6: User Story 3 — Dashboard: Pipeline Status & Deal History (Priority: P3)

**Goal**: MCP tools `get_pipeline_cycles`, `get_deals`, and `get_quota_usage` expose live pipeline data from `pipeline.log` and `processed_ids.json`.

**Independent Test**: With fixture log + state files: `get_pipeline_cycles()` → list of `PipelineCycle` dicts; `get_deals(status="all")` → list of `DealRecord` dicts; `get_quota_usage()` → `QuotaUsage` dict with correct `pct_used`.

### Tests for US3 (write first — must FAIL before implementation)

- [ ] T018 [P] [US3] Write `tests/unit/test_gateway_readers.py` — fixtures: tmp `pipeline.log` (5 JSONL lines) + tmp `processed_ids.json` (3 deal entries, 1 non-deal); test `read_pipeline_log(n=3)`: returns list of 3 `PipelineCycle` dicts; test `read_pipeline_log(n=100)`: returns all 5 lines; test missing log → `[]`; test `read_deals(limit=10, status_filter="all")`: returns 3 deal dicts; test `status_filter="crm_logged"` returns subset; test `compute_quota_usage()`: `cycles_today` correct, `pct_used = cycles_today / 1500 * 100`, `window_date == today`
- [ ] T019 [P] [US3] Write `tests/unit/test_gateway_tools_pipeline.py` (cycles/deals/quota section) — mock `readers` module; test `get_pipeline_cycles(limit=5)` returns `{"cycles": [...], "total_in_log": N}`; test `get_deals(limit=10, status="crm_logged")` returns `{"deals": [...], "total_deals": N, "filtered_by": "crm_logged"}`; test `get_quota_usage()` returns QuotaUsage dict with all 7 required keys

### Implementation for US3

- [ ] T020 [US3] Implement `src/openclaw_gateway/readers.py` — `read_pipeline_log(n: int) -> list[dict]`: open `PIPELINE_LOG_PATH` (from `GatewayConfig`), read last `n` JSONL lines (use `collections.deque(maxlen=n)`), parse each line as `PipelineCycle` dict; return `[]` on missing/empty file; `read_deals(limit: int, status_filter: str) -> list[dict]`: load `STATE_STORE_PATH` JSON, filter entries where `outcome == "deal_extracted"`, then apply `status_filter` against `crm_status` / `notify_status` if not `"all"`, return first `limit` as `DealRecord` dicts; `compute_quota_usage() -> dict`: count log lines with `window_date == date.today().isoformat()`, compute `pct_used`, build `QuotaUsage` dict with `has_quota_error_today` flag from any `error` field containing `"quota"`
- [ ] T021 [US3] Implement `get_pipeline_cycles(limit: int = 20)` in `src/openclaw_gateway/tools/pipeline.py` — calls `readers.read_pipeline_log(limit)`; reads all entries for `total_in_log` (separate `read_pipeline_log(n=99999)`); returns `{"cycles": cycles, "total_in_log": total}`
- [ ] T022 [P] [US3] Implement `get_deals(limit: int = 50, status: str = "all")` in `src/openclaw_gateway/tools/pipeline.py` — calls `readers.read_deals(limit, status)`; reads all deals for `total_deals` count; returns `{"deals": deals, "total_deals": total, "filtered_by": status}`
- [ ] T023 [P] [US3] Implement `get_quota_usage()` in `src/openclaw_gateway/tools/pipeline.py` — calls `readers.compute_quota_usage()`; returns `QuotaUsage` dict directly

**Checkpoint**: All 5 read-only MCP tools functional; dashboard data endpoints complete.

---

## Phase 7: User Story 4 — Manual Pipeline Trigger + Full Gateway Server (Priority: P4)

**Goal**: `run_cycle` MCP tool triggers a live pipeline run via `CycleLock`; the scheduler thread auto-runs on interval; `__main__.py` wires everything together so `python -m openclaw_gateway` starts a real HTTP MCP server.

**Independent Test**: `python -m openclaw_gateway` starts; `run_cycle` via HTTP returns `PipelineCycle` dict; second concurrent call returns `{"busy": true, ...}`; SIGTERM shuts down cleanly.

### Tests for US4 (write first — must FAIL before implementation)

- [ ] T024 [P] [US4] Write `tests/unit/test_gateway_scheduler.py` — test: `SchedulerThread` is `daemon=True`; test: calling `start()` then `stop()` within 0.1 s does not raise; test: with mocked `run_cycle` and a 0.01 s interval, `run_cycle` is called at least once within 0.1 s; test: `_stop_event.set()` exits the loop without additional `run_cycle()` calls
- [ ] T025 [P] [US4] Extend `tests/unit/test_gateway_tools_pipeline.py` (run_cycle section) — test busy path: pre-acquire lock file → `run_cycle()` returns `{"busy": True, "message": "..."}` containing "progress"; test success path: mock `OrchestratorRunner.run_once()` → returns `PipelineCycle` dict with all 7 required fields; test: `server._last_cycle_at` and `server._cycle_running` updated after success
- [ ] T026 [US4] Write `tests/integration/test_gateway_e2e.py` — fixture: start `subprocess.Popen(["python", "-m", "openclaw_gateway"])` with `SCHEDULER_MODE=gateway` and test env vars; poll `GET http://127.0.0.1:18790/health` until 200 (max 5 s); call `run_cycle` via MCP HTTP POST; assert response contains `emails_processed`; call `get_pipeline_cycles(limit=1)`; assert last cycle present; teardown: `proc.send_signal(SIGTERM)` + `proc.wait(timeout=5)`

### Implementation for US4

- [ ] T027 [US4] Implement `run_cycle()` in `src/openclaw_gateway/tools/pipeline.py` — attempt `portalocker.lock(lock_fh, portalocker.LOCK_EX | portalocker.LOCK_NB)`; on `portalocker.AlreadyLocked`: return `{"busy": True, "message": "Pipeline run already in progress"}`; on success: set `server._cycle_running = True`; call `pipeline_orchestrator.OrchestratorRunner(config).run_once()`; capture result as `PipelineCycle` dict; set `server._last_cycle_at = datetime.utcnow().isoformat()`, `server._cycle_running = False`; release lock; return `PipelineCycle` dict
- [ ] T028 [US4] Implement `src/openclaw_gateway/scheduler.py` — `class SchedulerThread(threading.Thread)` with `daemon = True` set in `__init__`; `_stop_event = threading.Event()`; `run(self)`: `while not self._stop_event.is_set(): run_cycle(); self._stop_event.wait(self.interval_seconds)` (blocking wait allows clean shutdown); `stop(self)`: `self._stop_event.set()`; `interval_seconds` from `GatewayConfig.scheduler_interval_seconds`
- [ ] T029 [US4] Implement `src/openclaw_gateway/__main__.py` — load `config = load_gateway_config()`; if `config.scheduler_mode == "gateway"`: create and start `SchedulerThread(config)`; register `signal.signal(SIGTERM, lambda *_: scheduler.stop())` for clean shutdown; set `server._gateway_start_time = time.time()`; call `mcp.run(transport="http", host=config.gateway_host, port=config.gateway_port)` in main thread (blocks until stopped)

**Checkpoint**: Full gateway server operational; all 6 MCP tools live; scheduler auto-cycles; US4 acceptance scenarios pass.

---

## Phase 8: Polish & Regression Gate

**Purpose**: Deploy wiring, final independence verification, full test sweep.

- [ ] T030 [P] Update `deploy/openclaw.service` — set `Type=simple`, change `ExecStart` to `python3.12 -m openclaw_gateway`, add `Environment=SCHEDULER_MODE=gateway`; remove any `--mode cron` flags from old ExecStart
- [ ] T031 [P] Confirm `tests/unit/test_claude_code_independence.py` (T008) passes against completed `src/openclaw_gateway/` — run `pytest tests/unit/test_claude_code_independence.py -v`; must report 0 matches and exit 0
- [ ] T032 Run full unit test suite `pytest tests/unit/ -v` — all tests green before integration
- [ ] T033 Run integration test `pytest tests/integration/test_gateway_e2e.py -v` — gateway starts, tools respond, SIGTERM clean; note: requires pipeline deps (`pipeline_orchestrator`) available in env

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Requires Phase 1 — **blocks all user story phases**
- **Phase 3 (US5)**: Requires Phase 2 only (stdlib test, no gateway imports)
- **Phase 4 (US1)**: Requires Phase 2; independent of US2/US3/US4
- **Phase 5 (US2)**: Requires Phase 2; independent of US1/US3/US4 (shares `tools/status.py` with US1 — implement after US1 to avoid file conflict)
- **Phase 6 (US3)**: Requires Phase 2; independent of US1/US2
- **Phase 7 (US4)**: Requires Phase 5 (needs `server.py` for shared state) and Phase 6 (needs `readers.py` and pipeline tool stubs); E2E test (T026) needs full gateway running
- **Phase 8 (Polish)**: Requires all user story phases complete

### Within-Phase Ordering

- Tests marked [P] within a phase: write all concurrently (different files)
- Implementation: `config.py` → `readers.py` → `tools/status.py` → `tools/pipeline.py` → `server.py` → `scheduler.py` → `__main__.py` → `cli.py`
- Each phase: tests written first (RED), then implementation (GREEN)

### Parallel Opportunities

- T003, T005 (Phase 1): fully parallel
- T006, T007 (Phase 2): parallel after T001–T002
- T009, T010 (US1 tests): parallel (different test files)
- T013, T014 (US2 tests): parallel
- T018, T019 (US3 tests): parallel
- T022, T023 (US3 impl): parallel (different functions in same file — coordinate)
- T024, T025 (US4 tests): parallel
- T030, T031 (Phase 8): parallel

---

## Implementation Strategy

### MVP Scope (US5 + US1 only)

1. Complete Phase 1 (Setup) → Phase 2 (Foundational)
2. Complete Phase 3 (US5) → independence gate live
3. Complete Phase 4 (US1) → `openclaw doctor` working
4. **Stop and validate**: `openclaw doctor` exit 0/1 per spec; independence test green
5. Ship this slice — `openclaw doctor` alone satisfies the P1 health-check user story

### Incremental Delivery

1. Setup + Foundational → Foundation
2. US5 → Independence gate (P1 — fast, just a test file)
3. US1 → `openclaw doctor` (P1 — 4 tasks)
4. US2 → `openclaw gateway status` + FastMCP server (P2 — 5 tasks)
5. US3 → Dashboard read tools (P3 — 6 tasks)
6. US4 → `run_cycle` + scheduler + `__main__.py` (P4 — 6 tasks + E2E)
7. Phase 8 → Systemd deploy + final sweep

### Task Counts by Phase

| Phase | Story | Priority | Tasks | Notes |
|-------|-------|----------|-------|-------|
| 1 | — | Setup | 5 | T001–T005 |
| 2 | — | Foundational | 2 | T006–T007 |
| 3 | US5 | P1 | 1 | T008 |
| 4 | US1 | P1 | 4 | T009–T012 |
| 5 | US2 | P2 | 5 | T013–T017 |
| 6 | US3 | P3 | 6 | T018–T023 |
| 7 | US4 | P4 | 6 | T024–T029 |
| 8 | — | Polish | 4 | T030–T033 |
| **Total** | | | **33** | |

---

## Notes

- [P] = parallelizable (different files, no incomplete-task dependencies)
- [USX] label maps each task to a user story for traceability
- Tests must be written and **FAIL** before implementation (TDD per constitution)
- US5 independence gate (T008) must remain green at every checkpoint — run it before each commit
- `tools/status.py` is shared by US1 (`get_health`) and US2 (`get_gateway_status`) — implement US1 functions first, add US2 functions in Phase 5 without removing Phase 4 work
- `tools/pipeline.py` functions accumulate across US3 (T021–T023) and US4 (T027) — coordinate writes to avoid conflicts
- Never commit `.env`, `credentials.json`, `processed_ids.json`, or `processed_ids.json.lock`
