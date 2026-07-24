# Research: 006-web-dashboard

**Date**: 2026-07-24 | **Branch**: `006-web-dashboard`

---

## Decision 1: How to Serve Static HTML from FastMCP

**Decision**: Add custom HTTP routes to FastMCP 3.4.4 using the `@mcp.custom_route()` decorator, serving the dashboard HTML file from `src/openclaw_gateway/static/dashboard.html`.

**Rationale**: FastMCP 3.4.4's `FastMCP` class exposes a `custom_route(path, methods)` decorator that registers Starlette `Route` objects alongside the MCP endpoint. This keeps everything in one uvicorn process, requires zero new dependencies, and avoids splitting the gateway into two separate servers. The dashboard file lives as a package resource under `src/openclaw_gateway/static/`, resolved via `importlib.resources` so it works when the package is installed editable or as a wheel.

**Alternatives considered**:
- *Separate HTTP server on a second port* — rejected: adds operational complexity (two processes, two ports to manage in systemd), conflicts with the zero-friction principle.
- *Inline dashboard HTML as a Python string constant* — rejected: makes the HTML uneditable without Python skills; poor separation of concerns.
- *Starlette `StaticFiles` mount* — workable but unnecessary; we only serve one file at `/`, not a directory of assets.

---

## Decision 2: Browser-to-Gateway Communication Protocol

**Decision**: Add five thin REST endpoints at `/api/*` that delegate to the existing tool implementation functions. The browser uses plain `fetch()` — no MCP protocol knowledge required.

**Rationale**: The MCP Streamable HTTP transport at `/mcp` requires a multi-step session handshake (initialize → session ID → tool call) that is complex to implement in vanilla JS without a library. Instead, five lightweight `GET`/`POST` handlers at `/api/status`, `/api/cycles`, `/api/deals`, `/api/quota`, `/api/run-cycle` wrap the exact same Python functions already used by the MCP tools. No business logic is duplicated — only the HTTP transport layer differs. The browser calls these with a one-line `fetch()`.

**Alternatives considered**:
- *Call `/mcp` directly from JS* — rejected: MCP Streamable HTTP requires session init (confirmed empirically: returns `"Missing session ID"` on bare POST), and implementing the handshake in vanilla JS without a library is brittle.
- *WebSockets* — rejected: overkill for a polling dashboard with 60-second refresh; no persistent push needed.
- *Server-Sent Events for live updates* — deferred: auto-refresh every 60 seconds (setInterval + fetch) meets SC-004 without SSE complexity.

---

## Decision 3: Single HTML File, Zero External Resources

**Decision**: The entire dashboard UI (HTML structure, CSS styles, JavaScript logic) lives in one file: `src/openclaw_gateway/static/dashboard.html`. No CDN, no npm, no build step.

**Rationale**: Constitution Principle I prohibits paid dependencies; zero-cost constraint means no CDN (potential availability risk). Self-contained single file means `openclaw dashboard` works with no internet access (SC-007). No build toolchain means no `node_modules`, no CI pipeline changes, no version pinning headaches. Modern browser ES6 + CSS variables + Fetch API provide everything needed for the dashboard UI.

**Alternatives considered**:
- *React + Vite* — rejected: introduces a build step, `node_modules`, and a dev server; over-engineered for a single-operator localhost tool.
- *Alpine.js or htmx from CDN* — rejected: violates zero-external-resources constraint (FR-022); CDN unavailability would break the dashboard.

---

## Decision 4: Auto-Refresh Strategy

**Decision**: `setInterval(refresh, 60_000)` in the dashboard JS, calling all five REST endpoints in parallel with `Promise.all(fetch(...))`. On each interval, the DOM is updated in-place — no full page reload.

**Rationale**: Meets SC-004 (data freshness within 60s) and US1 acceptance scenario 4 (silent in-place update) without any server-side push mechanism. `Promise.all` ensures all panels update atomically rather than staggered, preventing a brief visual inconsistency where, say, quota shows as OK while status shows DEGRADED.

**Alternatives considered**:
- *Full page reload every 60s* — rejected: disrupts any user interaction (e.g., mid-scroll through deals list).
- *WebSockets / SSE* — deferred; not needed for 60-second polling.

---

## Decision 5: Run Cycle — Browser Behaviour During Long Cycles

**Decision**: The "Run Cycle" button disables immediately on click. The browser polls `/api/status` every 2 seconds while `cycle_running: true`. When the cycle completes (detected via status poll), the browser fetches `/api/run-cycle` result from a cached response object, updates the UI, and re-enables the button. A 90-second client-side timeout shows a "still running — check logs" message without terminating the cycle.

**Rationale**: `run_cycle` is a synchronous blocking call on the server (can take 1–10 min). Holding a long `fetch()` open risks browser timeout and gives no progress feedback. Polling `/api/status` for `cycle_running` gives the operator a live indicator while the cycle runs, without requiring the browser to hold an open connection.

**Alternatives considered**:
- *Long-poll on `/api/run-cycle`* — rejected: browser HTTP timeouts typically fire at 30–120s; cycle can exceed that.
- *WebSockets for cycle progress* — deferred to future version.

---

## Decision 6: Dashboard File Path Resolution

**Decision**: Use `importlib.resources` (`importlib.resources.files("openclaw_gateway").joinpath("static/dashboard.html")`) to locate the HTML file at runtime. This works for editable installs, built wheels, and zipimport.

**Rationale**: Hardcoded relative paths break when the process working directory differs from the package source. `importlib.resources` is the correct stdlib mechanism for package data files in Python 3.12.

**Alternatives considered**:
- `Path(__file__).parent / "static" / "dashboard.html"` — works for editable installs but fails for namespace packages and zipimport; less future-proof.
