# ADR-0004: Gateway HTTP Transport Replaces Stdio Subprocess Model

- **Status:** Accepted
- **Date:** 2026-07-23
- **Feature:** mcp-dashboard (005-mcp-dashboard); supersedes orchestration-layer portion of ADR-0001
- **Context:** ADR-0001 established that each pipeline step (gmail_intake, crm_logger, discord_notifier) runs as a FastMCP subprocess over stdio, spawned by the host OpenClaw agent. This model works for individual MCP tool calls but cannot support a persistent HTTP server that the dashboard and CLI can reach independently. Feature 005 introduces a new `openclaw_gateway` orchestration layer that must remain running between requests to (a) serve the OpenClaw built-in dashboard at `http://127.0.0.1:18789`, (b) accept out-of-band `run_cycle` triggers from the dashboard, and (c) respond to `openclaw gateway status` CLI calls at any time. A persistent HTTP binding cannot be achieved with the stdio subprocess model. The decision affects the gateway layer only — the individual step packages retain their FastMCP stdio interfaces unchanged (they are now called as Python functions internally, not spawned as subprocesses by the orchestrator).

## Decision

The `openclaw_gateway` package exposes an MCP server using **FastMCP 3.4.4 HTTP transport** (`transport="http"`) bound to a configurable host and port (default `127.0.0.1:18789`):

- **MCP framework**: `fastmcp>=2.0` (unchanged dependency; only the transport mode changes)
- **Transport**: HTTP via uvicorn/ASGI — `mcp.run(transport="http", host=host, port=port)`
- **MCP endpoint**: `/mcp` (FastMCP default)
- **Dashboard**: OpenClaw built-in UI served at `http://127.0.0.1:18789` by FastMCP's HTTP server
- **Bind address**: Configurable via `GATEWAY_HOST` (default `127.0.0.1`) and `GATEWAY_PORT` (default `18789`)
- **Step invocation**: Gateway calls existing `pipeline_orchestrator.runner.run_cycle()` as a Python function — steps are NOT spawned as subprocesses by the gateway

ADR-0001's stdio subprocess model continues to apply to the individual step packages if they are used standalone (e.g., during development or testing). At runtime in gateway mode, steps are wired via direct Python function calls inside `run_cycle()`.

## Consequences

### Positive

- Gateway remains addressable between requests — enables dashboard polling, CLI queries, and out-of-band `run_cycle` triggers.
- Zero new dependencies: FastMCP 3.4.4 already supports HTTP transport with uvicorn; no Flask/FastAPI needed.
- OpenClaw's built-in dashboard UI is served by the same FastMCP HTTP server at the same port — one process, one port.
- Operator deployment is simpler: one `systemd Type=simple` service instead of a Node.js host + Python child process model.
- Individual step packages remain independently testable with their existing stdio/direct-call test harnesses.

### Negative

- HTTP transport introduces a long-running network listener; any port conflict (e.g., another process on 18789) will prevent gateway startup. Requires operator awareness of port allocation.
- The gateway is no longer crash-isolated from its MCP tools: a tool panic that escapes its exception handler could crash the HTTP server. The stdio model isolated each tool in its own process.
- Persistent HTTP binding means the gateway must be explicitly managed (systemd start/stop); the previous one-shot subprocess model was stateless and self-terminating.
- Partial supersession of ADR-0001 at the orchestration layer adds model complexity: developers must understand two transport modes (stdio for standalone steps, HTTP for the gateway).

## Alternatives Considered

**Alternative A: Retain stdio subprocess model, add a thin HTTP proxy**
Wrap the existing subprocess-per-call model in a Node.js or Python HTTP server that translates HTTP requests to stdio MCP calls. Rejected: requires an additional long-running process (the proxy) and adds complexity without benefit, since FastMCP already provides HTTP transport natively.

**Alternative B: Separate HTTP framework (Flask or FastAPI)**
Add Flask or FastAPI as the HTTP server, serving a REST API instead of MCP tools. Rejected: (a) adds a new dependency not in the existing project, violating the spirit of Constitution Principle I (minimum footprint); (b) loses the MCP tool contract, breaking integration with any MCP client including the OpenClaw dashboard.

**Alternative C: Keep stdio, poll via file (log-based status)**
Dashboard reads `pipeline.log` directly; no HTTP server needed; `run_cycle` trigger done via a sentinel file. Rejected: sentinel files are a fragile IPC mechanism; real-time state updates (FR-014, cycle-in-progress indicator) are not achievable without a push channel or tight polling interval.

## References

- Feature Spec: `specs/005-mcp-dashboard/spec.md`
- Implementation Plan: `specs/005-mcp-dashboard/plan.md` (Decision 1)
- Research: `specs/005-mcp-dashboard/research.md` (Decision 1 — FastMCP HTTP Transport)
- Related ADRs: ADR-0001 (superseded at orchestration layer), ADR-0005 (scheduler architecture that depends on this HTTP model)
- Evaluator Evidence: `history/prompts/005-mcp-dashboard/0002-mcp-gateway-dashboard-plan-complete.plan.prompt.md`
