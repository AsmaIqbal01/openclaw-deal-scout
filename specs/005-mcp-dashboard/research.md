# Phase 0 Research: OpenClaw MCP Gateway + Dashboard

**Branch**: `005-mcp-dashboard` | **Date**: 2026-07-23

---

## Decision 1 — FastMCP HTTP Transport

**Decision**: Use FastMCP 3.4.4 `transport="http"` with `host` and `port` kwargs to run the gateway as a persistent HTTP server on port 18789.

**Evidence**: `mcp.run(transport="http", host=host, port=port)` is a valid call in FastMCP 3.4.4. The `run_http_async()` method accepts `host: str | None` and `port: int | None`. The HTTP server is powered by uvicorn (ASGI). MCP protocol endpoint is served at `/mcp` by default.

**Rationale**: HTTP transport is the only mode that (a) allows the gateway to remain running as a persistent service accessible to the dashboard and CLI, (b) is included in the existing `fastmcp>=2.0` dependency already in `pyproject.toml`, and (c) requires zero paid infrastructure.

**Alternatives considered**:
- `stdio` transport: process-per-call model; cannot serve a persistent HTTP endpoint. Ruled out.
- Separate HTTP framework (Flask/FastAPI): adds a paid or heavyweight dependency not already in the project. Ruled out by Constitution Principle I.

---

## Decision 2 — Gateway Package Architecture

**Decision**: New `src/openclaw_gateway/` Python package alongside the existing four packages. Entry point: `python -m openclaw_gateway` (or `openclaw` CLI command after install).

**Rationale**: Mirrors the existing package structure (`gmail_intake`, `crm_logger`, `discord_notifier`, `pipeline_orchestrator`). Each package is independently testable. The gateway is a **wiring layer only** — it imports and calls existing orchestrator functions without modifying them.

**Internal module layout**:
```
src/openclaw_gateway/
├── __init__.py          — public exports
├── __main__.py          — entry point: parse env → start HTTP server
├── server.py            — FastMCP instance + tool registrations
├── scheduler.py         — background scheduler thread (SCHEDULER_MODE=loop)
├── tools/
│   ├── __init__.py
│   ├── status.py        — get_gateway_status(), get_health() tools
│   └── pipeline.py      — run_cycle(), get_cycles(), get_deals(), get_quota_usage() tools
├── readers.py           — read state store + pipeline.log (read-only, with portalocker)
└── cli.py               — argparse-based `openclaw` CLI (gateway status, dashboard, doctor)
```

**Alternatives considered**:
- Monolithic `server.py` with all tools inline: harder to unit-test individual tools. Ruled out.
- Separate `src/openclaw_cli/` package: unnecessary split; CLI and gateway share config and readers. Ruled out.

---

## Decision 3 — Scheduler Integration Strategy

**Decision**: Gateway handles both HTTP serving and pipeline scheduling in a single process. The background scheduler runs in a `threading.Thread`; FastMCP HTTP runs in the main thread (via uvicorn/anyio). SCHEDULER_MODE env var controls behaviour:

| Mode | Behaviour |
|------|-----------|
| `gateway` (new) | FastMCP HTTP on 18789 + background scheduler loop |
| `systemd` (existing) | One-shot cycle via `pipeline_orchestrator` (unchanged) |
| `loop` (existing) | Sleep loop via `pipeline_orchestrator` (unchanged) |

The `openclaw.service` systemd unit switches from `Type=oneshot` to `Type=simple` and invokes `python -m openclaw_gateway` with `SCHEDULER_MODE=gateway`.

**Rationale**: A single gateway process manages HTTP + scheduling without requiring a second systemd service. Keeps operator config minimal: one service file, one process.

**Concurrent-cycle safety**: The `run_cycle` MCP tool calls `pipeline_orchestrator.runner.run_cycle()` which already holds a `CycleLock`. If the background scheduler is mid-cycle when a manual `run_cycle` is triggered, the lock raises `CycleLockActiveError` → tool returns `busy` response. No double-cycle risk.

**Alternatives considered**:
- Two processes (gateway HTTP-only + existing systemd timer): clean separation but `run_cycle` MCP tool can't synchronously return cycle results, only trigger. Ruled out because FR-003 requires `run_cycle` to return a cycle summary.
- Asyncio background task instead of thread: FastMCP's HTTP server runs the event loop; a parallel asyncio background task is cleaner, but `run_cycle` calls blocking I/O (`asyncio.run()`) internally. Thread avoids event-loop nesting. Thread chosen.

---

## Decision 4 — CLI Installation

**Decision**: Register `openclaw` as a console script entry point in `pyproject.toml`. After `pip install -e .`, `openclaw` is on PATH as a system command. Uses stdlib `argparse`; no new dependencies.

```toml
[project.scripts]
openclaw = "openclaw_gateway.cli:main"
```

**Subcommands**:
- `openclaw gateway status` → HTTP GET to `http://127.0.0.1:18789/health` (or MCP tool call)
- `openclaw dashboard` → `webbrowser.open("http://127.0.0.1:18789")`
- `openclaw doctor` → direct credential/service checks (does NOT require gateway to be running)

**Rationale**: Entry-point scripts are the standard Python pattern for CLI tools. stdlib `webbrowser` for `dashboard` open means zero new dependencies. `doctor` operates independently of the gateway (checks credentials directly) so it works even when the gateway is stopped.

**Alternatives considered**:
- Shell script alias (`/usr/local/bin/openclaw`): fragile, non-portable, doesn't install cleanly with pip. Ruled out.
- Typer or Click CLI framework: adds a non-stdlib dependency. Ruled out by Constitution Principle I.

---

## Decision 5 — MCP Tools Surface

**Decision**: Six MCP tools exposed by the gateway:

| Tool | Input | Output | Reads |
|------|-------|--------|-------|
| `get_gateway_status` | — | GatewayStatus | gateway process state |
| `run_cycle` | — | PipelineCycle | triggers runner.run_cycle() |
| `get_pipeline_cycles` | limit: int = 20 | list[PipelineCycle] | pipeline.log |
| `get_deals` | limit: int = 50, status: str = "all" | list[DealRecord] | processed_ids.json |
| `get_quota_usage` | — | QuotaUsage | pipeline.log (request count estimate) |
| `get_health` | — | HealthCheckReport | credentials + live service pings |

**Rationale**: These six cover the five dashboard display requirements (FR-014 through FR-017) and the manual trigger (FR-018). `get_gateway_status` powers `openclaw gateway status`. `get_health` powers `openclaw doctor`.

**State store reads**: Read-only access to `processed_ids.json` via `portalocker.lock(f, portalocker.LOCK_SH)` (shared lock) to avoid corrupting writes from the pipeline. The pipeline's state-store writers use `portalocker.LOCK_EX` already.

**Alternatives considered**:
- Resources (MCP resources API) instead of tools: resources are read-only by convention and not interactive; using tools keeps the surface consistent with existing packages. Tools chosen.

---

## Decision 6 — Claude Code Independence Gate

**Decision**: Enforce zero Claude Code references via an automated grep test added to the test suite.

**Current state**: `grep -r 'claude|anthropic|ANTHROPIC|CLAUDE' src/` → **CLEAN** (0 matches confirmed).

**Gate mechanism**: New test `tests/unit/test_claude_code_independence.py` runs the grep programmatically and asserts zero matches. Fails the test suite if any production source file imports or references Claude Code tooling.

**Rationale**: A runtime test is more reliable than a pre-commit hook or documentation. It runs in CI with every `pytest` invocation and cannot be silently bypassed.

---

## Decision 7 — Port and Bind Address

**Decision**: Gateway binds to `127.0.0.1:18789` by default. Controlled via two env vars:

| Env Var | Default | Purpose |
|---------|---------|---------|
| `GATEWAY_HOST` | `127.0.0.1` | Bind address (set to `0.0.0.0` for LAN access) |
| `GATEWAY_PORT` | `18789` | Port (matches OpenClaw built-in dashboard port) |

Both are validated at startup (port must be integer 1024–65535; host must be non-empty string).

**Rationale**: Port 18789 matches the OpenClaw built-in dashboard address the user specified. Making both configurable via env vars satisfies FR-013 without code changes for LAN deployments.
