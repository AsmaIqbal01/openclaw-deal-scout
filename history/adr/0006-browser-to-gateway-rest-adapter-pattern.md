# ADR-0006: Browser-to-Gateway REST Adapter Pattern

- **Status:** Accepted
- **Date:** 2026-07-24
- **Feature:** 006-web-dashboard

**Context:** The OpenClaw dashboard browser needs to read live pipeline data from the FastMCP gateway (port 18790) and trigger pipeline cycles. The gateway's primary protocol is MCP Streamable HTTP at `/mcp`. The question is: how should the browser communicate with the gateway?

The MCP Streamable HTTP transport requires a stateful session handshake: the client must first POST an `initialize` message to `/mcp`, receive a `session_id` in response, then include that `session_id` header on every subsequent tool call. This multi-step protocol is designed for persistent MCP client libraries (Python, TypeScript SDK), not browser fetch(). Implementing it correctly in vanilla JS without a library requires handling SSE streams, session lifecycle, and error recovery — a significant undertaking that couples the dashboard to the MCP protocol's internal conventions.

The gateway is a single Python process running under FastMCP 3.4.4 (Starlette underneath). No new Python process or port is permitted (zero-infra constraint). All six MCP tools already have well-tested Python implementation functions that are called by the MCP tool handlers.

**Significance checklist:**
1. Impact: Yes — determines how all current and future browser clients communicate with the gateway; any new dashboard feature must follow this pattern
2. Alternatives: Yes — three distinct approaches considered with different protocol and maintenance tradeoffs
3. Scope: Yes — cross-cutting; affects server.py, routes/, dashboard.html, and any future browser-based tooling

## Decision

Add five thin REST endpoints to the existing FastMCP gateway using the `@mcp.custom_route()` decorator (FastMCP 3.4.4 API). These endpoints delegate directly to the existing MCP tool implementation functions — no business logic is duplicated.

**Endpoint cluster:**
- `GET /` — serves `dashboard.html` via `importlib.resources`
- `GET /api/status` — delegates to `get_gateway_status()` + `get_health()`
- `GET /api/cycles` — delegates to `get_pipeline_cycles(limit)`
- `GET /api/deals` — delegates to `get_deals(limit, status)`
- `GET /api/quota` — delegates to `get_quota_usage()`
- `POST /api/run-cycle` — delegates to `run_cycle()`

**Implementation surface:**
- New module: `src/openclaw_gateway/routes/api.py` (six async Starlette route handlers)
- Modified: `src/openclaw_gateway/server.py` (registers custom routes on the `mcp` instance)
- New package data: `src/openclaw_gateway/static/dashboard.html`

The browser uses plain `fetch()` with no library, no session management, no MCP protocol knowledge. All responses are JSON (or HTML for `GET /`). CORS header `Access-Control-Allow-Origin: *` on all `/api/*` endpoints.

## Consequences

### Positive

- **Zero protocol complexity in the browser**: `fetch('/api/status')` is one line; no session init, no SSE parsing, no session ID header management
- **Zero new Python dependencies**: `@mcp.custom_route` is part of FastMCP 3.4.4 already installed; Starlette is a transitive dep
- **Thin adapter, no logic duplication**: REST handlers call the same implementation functions as MCP tools; a bug fix to `get_deals()` is automatically reflected in both the MCP tool and the REST endpoint
- **Independently testable**: REST handlers can be unit-tested by calling them with mock Starlette `Request` objects, same as any Starlette view
- **Future-proof**: Any future browser client (mobile web, Electron, Tauri) can use the same `/api/*` endpoints without implementing MCP protocol
- **Debuggable with curl**: `curl http://127.0.0.1:18790/api/status` works immediately; no session bootstrap required

### Negative

- **Parallel protocol surfaces**: Two ways to call the same logic — MCP tools (for AI agents/CLI) and REST endpoints (for browser). A new tool implementation must be wired into both if browser access is needed
- **Non-standard**: `/api/*` REST is not the "MCP way"; if FastMCP ever offers a built-in browser adapter, this custom layer becomes redundant
- **No streaming**: REST polling every 60s means dashboard data is up to 60s stale; MCP SSE could theoretically push real-time updates (but this is out of scope for a single-operator local tool)
- **CORS surface**: `Access-Control-Allow-Origin: *` on a localhost server is safe for this use case but must be tightened if the gateway is ever exposed beyond localhost

## Alternatives Considered

### Alternative A: Call `/mcp` directly from browser vanilla JS

Implement the MCP Streamable HTTP session handshake in plain JavaScript inside `dashboard.html`.

- **Why rejected**: MCP Streamable HTTP requires sending `initialize` with capabilities, receiving `session_id` from the response stream, then including it as a header on every subsequent POST. Empirically confirmed: bare POST to `/mcp` returns `{"error": "Missing session ID"}`. Implementing this without a library adds ~200 lines of brittle protocol glue to the dashboard, and couples the dashboard to MCP protocol internals that may change between FastMCP versions.

### Alternative B: WebSockets for live push

Add a WebSocket endpoint to the gateway; browser subscribes to push events as pipeline state changes.

- **Why rejected (deferred)**: No push events exist in the current pipeline — state only changes during a cycle run. WebSockets would require implementing an event bus within the gateway process. For a 60-second polling interval serving a single operator, the complexity/benefit ratio is poor. Deferred to a future version if real-time push becomes a requirement.

### Alternative C: Separate lightweight HTTP server on a second port

Run a separate Python `http.server` or Starlette app on a second port (e.g., 18791) that serves only dashboard endpoints.

- **Why rejected**: Violates the zero-new-processes constraint (one systemd unit, one process). Two ports means two ports to firewall, two ports to document, two services to monitor. The `@mcp.custom_route` API exists precisely to avoid this split.

### Alternative D: Server-Sent Events (SSE) for auto-refresh

Instead of `setInterval` polling, the gateway pushes SSE events whenever pipeline state changes.

- **Why rejected (deferred)**: Same reasoning as Alternative B — no push events exist today. SSE requires either a message queue within the gateway or a polling loop inside the server-side SSE handler. For a 60-second refresh interval on a single-machine tool, `setInterval + fetch` is simpler and sufficient. Can be layered on top of this REST foundation later without changing the client protocol.

## References

- Feature Spec: `specs/006-web-dashboard/spec.md`
- Implementation Plan: `specs/006-web-dashboard/plan.md`
- REST API Contracts: `specs/006-web-dashboard/contracts/dashboard-api.md`
- Research (Decision 2): `specs/006-web-dashboard/research.md`
- Related ADRs: ADR-0004 (gateway-http-transport), ADR-0005 (gateway-scheduler-architecture)
- Evaluator Evidence: `history/prompts/006-web-dashboard/0002-web-dashboard-plan-complete.plan.prompt.md`
