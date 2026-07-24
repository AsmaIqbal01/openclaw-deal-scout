# Tasks: 006-web-dashboard

**Feature**: Web Dashboard for OpenClaw Deal Scout
**Branch**: `006-web-dashboard`
**Input**: `specs/006-web-dashboard/` (spec.md, plan.md, research.md, data-model.md, contracts/dashboard-api.md)
**Date**: 2026-07-24

**Stack**: Python 3.12 (gateway); HTML5 + CSS3 + ES6 JS (dashboard); FastMCP 3.4.4 (`@mcp.custom_route`); Starlette; `importlib.resources`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Exact file paths included in every description

---

## Phase 1: Setup (Project Structure)

**Purpose**: Create the new directories and configuration changes that all subsequent tasks depend on.

- [ ] T001 Create `src/openclaw_gateway/static/dashboard.html` with minimal placeholder HTML (`<!doctype html><html><head><title>OpenClaw Dashboard</title></head><body><h1>OpenClaw Dashboard</h1></body></html>`) — full content added in Phase 3+
- [ ] T002 [P] Create `src/openclaw_gateway/routes/__init__.py` as an empty file (makes `routes/` a Python package)
- [ ] T003 [P] Add `[tool.setuptools.package-data]` entry `"openclaw_gateway" = ["static/*"]` to `pyproject.toml` so `dashboard.html` is included in editable and wheel installs

**Checkpoint**: `src/openclaw_gateway/static/` and `src/openclaw_gateway/routes/` exist; `pyproject.toml` includes package-data entry.

---

## Phase 2: Foundational (REST API Layer — blocks all user stories)

**Purpose**: Wire the five REST endpoints and the HTML-serving route into the gateway. All user stories (US1–US4) depend on these endpoints being callable.

**⚠️ CRITICAL**: No user story dashboard work can begin until T011 is complete and the gateway starts without error.

- [ ] T004 Implement shared `_json_response(data, status=200)` helper that wraps `JSONResponse` and adds `Access-Control-Allow-Origin: *` header; implement `_error(msg, endpoint)` helper returning `{"error": msg, "endpoint": endpoint}` in `src/openclaw_gateway/routes/api.py`
- [ ] T005 [P] Implement `serve_dashboard(request)` handler: reads `src/openclaw_gateway/static/dashboard.html` via `importlib.resources.files("openclaw_gateway").joinpath("static/dashboard.html").read_text()`, returns `HTMLResponse`; raises HTTP 500 if file cannot be read in `src/openclaw_gateway/routes/api.py`
- [ ] T006 [P] Implement `api_status(request)` handler: calls `get_gateway_status(config)` and `get_health(config)` from `openclaw_gateway.tools.status`, returns `{"gateway": ..., "health": ...}` via `_json_response()` in `src/openclaw_gateway/routes/api.py`
- [ ] T007 [P] Implement `api_cycles(request)` handler: reads optional `limit` query param (default 20, clamp 1–100), delegates to `get_pipeline_cycles(limit=limit)` from `openclaw_gateway.tools.pipeline`, wraps result in `_json_response()` in `src/openclaw_gateway/routes/api.py`
- [ ] T008 [P] Implement `api_deals(request)` handler: reads `status` (default `"all"`) and `limit` (default 50, clamp 1–500) query params; returns HTTP 400 via `JSONResponse({"error": "..."}, status_code=400)` for invalid status values; delegates to `get_deals(limit=limit, status=status)` in `src/openclaw_gateway/routes/api.py`
- [ ] T009 [P] Implement `api_quota(request)` handler: delegates to `get_quota_usage()` from `openclaw_gateway.tools.pipeline`, wraps result in `_json_response()` in `src/openclaw_gateway/routes/api.py`
- [ ] T010 [P] Implement `api_run_cycle(request)` handler: delegates to `run_cycle()` from `openclaw_gateway.tools.pipeline`; catches `CycleLockActiveError` → returns `{"busy": true, "message": "..."}` via `_json_response()`; catches general `Exception` → returns `{"error": str(e), "ts": "..."}` via `_json_response()` in `src/openclaw_gateway/routes/api.py`
- [ ] T011 Register all six custom routes on the `mcp` instance in `src/openclaw_gateway/server.py` using `@mcp.custom_route(path, methods=[...])` decorators: `GET /` → `serve_dashboard`, `GET /api/status` → `api_status`, `GET /api/cycles` → `api_cycles`, `GET /api/deals` → `api_deals`, `GET /api/quota` → `api_quota`, `POST /api/run-cycle` → `api_run_cycle`
- [ ] T012 [P] Write unit tests for `serve_dashboard` handler (HTML response, Content-Type header, 500 on missing file) and `api_status` handler (returns merged gateway+health dict, includes CORS header) in `tests/unit/test_dashboard_routes.py`
- [ ] T013 [P] Write unit tests for `api_cycles` handler (default limit, custom limit, clamping) and `api_deals` handler (valid status values, invalid status → 400, default params) in `tests/unit/test_dashboard_routes.py`
- [ ] T014 [P] Write unit tests for `api_quota` handler (returns quota dict, CORS header) and `api_run_cycle` handler (success path, busy path `CycleLockActiveError`, error path) in `tests/unit/test_dashboard_routes.py`
- [ ] T015 Write smoke test asserting `importlib.resources.files("openclaw_gateway").joinpath("static/dashboard.html")` is readable and returns non-empty content in `tests/unit/test_dashboard_html.py`
- [ ] T016 Run `pytest tests/unit/ -x` — all 279 existing tests plus new route tests must pass before proceeding to user story phases

**Checkpoint**: `curl http://127.0.0.1:18790/` returns 200 with HTML; `curl http://127.0.0.1:18790/api/status` returns JSON with `gateway` and `health` keys; full test suite green.

---

## Phase 3: User Story 1 — Pipeline Status at a Glance (Priority: P1) 🎯 MVP

**Goal**: Operator opens dashboard and immediately sees pipeline health (HEALTHY/DEGRADED), uptime, last cycle time, component breakdown, and recent cycles — no terminal required.

**Independent Test**: Start gateway, open `http://127.0.0.1:18790`. Status panel must show overall health badge, uptime in "Xh Ym" format, last-cycle timestamp (or "Never"), cycle-running indicator, and a grid of 6 components (gmail, gemini, hubspot, discord, state_store, log) each with PASS/FAIL indicator. Cycles table must show the 20 most recent cycles with timestamp, emails, CRM, notify, and error columns.

- [ ] T017 [US1] Add HTML skeleton for status panel — `<section id="status-panel">` containing: `<span id="health-badge">`, `<span id="uptime">`, `<span id="last-cycle">`, `<div id="cycle-running-indicator" hidden>`, and `<div id="component-grid">` — in `src/openclaw_gateway/static/dashboard.html`
- [ ] T018 [US1] Add HTML skeleton for recent cycles panel — `<section id="cycles-panel">` containing `<table id="cycles-table">` with `<thead>` columns: Timestamp, Emails, CRM, Notified, Errors — in `src/openclaw_gateway/static/dashboard.html`
- [ ] T019 [US1] Write `fetchJSON(url)` async helper (calls `fetch(url)`, throws on non-OK, returns parsed JSON) in the `<script>` block of `src/openclaw_gateway/static/dashboard.html`
- [ ] T020 [US1] Write `humanUptime(seconds)` helper returning strings like "2h 14m" and `fmtTs(isoString)` returning locale time string in `src/openclaw_gateway/static/dashboard.html`
- [ ] T021 [US1] Write `renderStatus(data)` function: sets `health-badge` text and CSS class (`healthy`/`degraded`), sets `uptime` text via `humanUptime()`, sets `last-cycle` via `fmtTs()` or "Never", shows/hides `cycle-running-indicator`, populates `component-grid` with one element per component in `src/openclaw_gateway/static/dashboard.html`
- [ ] T022 [US1] Write `renderCycles(data)` function: clears and repopulates `cycles-table` tbody with one row per cycle (newest-first), showing timestamp, emails_processed, crm_logged, notified, and errors joined as comma-separated string or "—" if empty in `src/openclaw_gateway/static/dashboard.html`
- [ ] T023 [US1] Write `refresh()` async function calling `Promise.all([fetchJSON('/api/status'), fetchJSON('/api/cycles?limit=20')])` and calling `renderStatus()` + `renderCycles()` + `updateTimestamp()` on resolution; call `refresh()` on `DOMContentLoaded` in `src/openclaw_gateway/static/dashboard.html`
- [ ] T024 [US1] Add CSS for status panel: `.healthy` badge (green background), `.degraded` badge (red background), component grid (2-column or 3-column flex), cycle-running indicator (animated pulse or blinking dot), cycles table row styling in `src/openclaw_gateway/static/dashboard.html`

**Checkpoint**: Open `http://127.0.0.1:18790`. Health badge, uptime, last-cycle, component grid, and cycles table all populate with real data from the running gateway. DEGRADED state visible when a component is down.

---

## Phase 4: User Story 2 — Deal Records and Status Filtering (Priority: P2)

**Goal**: Operator can view detected deals and filter them by status without touching the state store file.

**Independent Test**: With at least three deals at mixed statuses in the state store, open the dashboard. Switch the filter dropdown between all six status options — each switch updates the deal rows and count to match only that status. Empty filter shows "No deals found" message.

- [ ] T025 [US2] Add HTML skeleton for deals panel — `<section id="deals-panel">` containing: `<select id="deal-filter">` with options all/crm_pending/crm_failed/notify_pending/notify_failed/complete, `<span id="deals-count">`, `<table id="deals-table">` with `<thead>` columns: Sender, Subject, CRM, Notified, Detected — in `src/openclaw_gateway/static/dashboard.html`
- [ ] T026 [US2] Write `renderDeals(data)` function: clears and repopulates `deals-table` tbody with one row per deal; sets `deals-count` text to `"${data.total_deals} deal(s)"`; shows `<tr id="no-deals-row"><td colspan="5">No deals found</td></tr>` when `data.deals.length === 0` in `src/openclaw_gateway/static/dashboard.html`
- [ ] T027 [US2] Add `let currentFilter = 'all'` state variable and `onFilterChange(event)` handler that updates `currentFilter`, fetches `/api/deals?status=${currentFilter}&limit=50`, calls `renderDeals()` in `src/openclaw_gateway/static/dashboard.html`; bind `onFilterChange` to `deal-filter` `change` event on `DOMContentLoaded`
- [ ] T028 [US2] Update `refresh()` to add `fetchJSON('/api/deals?status=${currentFilter}&limit=50')` as a third item in the `Promise.all` array; pass the result to `renderDeals()` in `src/openclaw_gateway/static/dashboard.html`
- [ ] T029 [US2] Add CSS for deal rows: CRM/notify status badges (`logged` → green, `pending` → yellow, `failed` → red), alternating row backgrounds, deals table `overflow-x: auto` container in `src/openclaw_gateway/static/dashboard.html`

**Checkpoint**: Filter dropdown works. Each of the 6 status options returns correct subset. Deal count updates. Empty state message shown when no matching deals. All deal row fields visible.

---

## Phase 5: User Story 3 — Manual Pipeline Trigger (Priority: P3)

**Goal**: Operator clicks "Run Cycle" from the dashboard and sees a cycle execute and its result — no SSH or CLI required.

**Independent Test**: With gateway running, click Run Cycle. Button disables immediately. Within 30 seconds, a result banner shows emails-processed / CRM-logged / notified counts. Button re-enables. Clicking while busy shows "pipeline busy" message. 90-second timeout shows "still running — check pipeline.log" message.

- [ ] T030 [US3] Add `<button id="run-cycle-btn">Run Cycle</button>` to the dashboard `<header>` and `<div id="cycle-result" hidden></div>` result banner below it in `src/openclaw_gateway/static/dashboard.html`
- [ ] T031 [US3] Write `runCycle()` async function: set `run-cycle-btn.disabled = true`, show spinner text ("Running…"), POST to `/api/run-cycle` via `fetchJSON`; on success → render result banner with counts (emails, CRM, notified, errors); on busy → show "Pipeline busy — try again shortly"; on error → show error message; call `refresh()` after result; re-enable button in `src/openclaw_gateway/static/dashboard.html`
- [ ] T032 [US3] Add 90-second client-side timeout to `runCycle()` using `AbortController` with `setTimeout(controller.abort, 90_000)`; on `AbortError` catch: show "Cycle still running — check pipeline.log for progress", poll `/api/status` every 2s until `cycle_running === false`, then re-enable button in `src/openclaw_gateway/static/dashboard.html`
- [ ] T033 [US3] On page load in `DOMContentLoaded` handler: after first `refresh()` resolves, disable `run-cycle-btn` immediately if `status.gateway.cycle_running === true`; update `renderStatus()` to also toggle button disabled state based on `data.gateway.cycle_running` in `src/openclaw_gateway/static/dashboard.html`
- [ ] T034 [US3] Add CSS for Run Cycle button states: default (blue/primary), disabled (grey, `cursor: not-allowed`), loading (spinner animation via `::after` or text change), result banner success (green border), busy (yellow border), error (red border) in `src/openclaw_gateway/static/dashboard.html`

**Checkpoint**: Run Cycle button disables on click, shows result banner on completion, re-enables. Busy path returns "pipeline busy" message. Timeout path shows "check pipeline.log" message and polls until cycle finishes.

---

## Phase 6: User Story 4 — Gemini Quota Awareness (Priority: P4)

**Goal**: Operator can see today's Gemini API quota consumption without reading log files.

**Independent Test**: With cycles run today, open the dashboard. Quota panel shows requests-used, 1500 limit, percentage, and a progress bar scaled to that percentage. If `has_quota_error_today` is true, a warning banner is visible.

- [ ] T035 [US4] Add HTML skeleton for quota panel — `<section id="quota-panel">` containing: `<div id="quota-bar-container"><div id="quota-bar"></div></div>`, `<span id="quota-used">`, `<span id="quota-limit">1500</span>`, `<span id="quota-pct">`, `<div id="quota-warning" hidden>⚠ Quota hit today — extraction skipped for some cycles</div>` — in `src/openclaw_gateway/static/dashboard.html`
- [ ] T036 [US4] Write `renderQuota(data)` function: sets `quota-bar` `width` to `${data.pct_used}%`, sets `quota-used` text, sets `quota-pct` text (`${data.pct_used}%`), shows/hides `quota-warning` based on `data.has_quota_error_today`, applies CSS class `quota-warn` (>75%) or `quota-danger` (>90%) to `quota-bar` in `src/openclaw_gateway/static/dashboard.html`
- [ ] T037 [US4] Update `refresh()` to add `fetchJSON('/api/quota')` to the `Promise.all` array; pass result to `renderQuota()` in `src/openclaw_gateway/static/dashboard.html`
- [ ] T038 [US4] Add CSS for quota panel: `quota-bar-container` (full-width grey track), `quota-bar` (filled portion, `transition: width 0.3s ease`), colour states: default (green), `.quota-warn` (yellow at >75%), `.quota-danger` (red at >90%), `quota-warning` banner (amber background, bold text) in `src/openclaw_gateway/static/dashboard.html`

**Checkpoint**: Quota panel shows correct values from `/api/quota`. Progress bar width reflects `pct_used`. Warning banner appears when `has_quota_error_today` is true.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cross-cutting improvements — offline state, auto-refresh, theming, meta tags, final test run.

- [ ] T039 Add `<div id="offline-banner" hidden>⚠ Gateway offline — data may be stale. Retrying…</div>` to `<header>` in `src/openclaw_gateway/static/dashboard.html`; update `refresh()` to catch fetch errors: show `offline-banner` on any network failure, hide it on next successful refresh
- [ ] T040 Add `let refreshTimer = setInterval(refresh, 60_000)` after `DOMContentLoaded` call; add `<span id="last-updated"></span>` to header; write `updateTimestamp()` setting it to `"Last updated: " + new Date().toLocaleTimeString()` in `src/openclaw_gateway/static/dashboard.html`
- [ ] T041 [P] Add CSS custom properties (`--bg`, `--surface`, `--text`, `--border`, `--accent-green`, `--accent-red`, `--accent-yellow`) in `:root` with light-mode defaults; add `@media (prefers-color-scheme: dark) { :root { ... } }` block with dark values; use `var(--*)` throughout all colour rules in `src/openclaw_gateway/static/dashboard.html`
- [ ] T042 [P] Add `<meta charset="utf-8">`, `<meta name="viewport" content="width=device-width, initial-scale=1">`, and verify `<title>OpenClaw Dashboard</title>` is present in `<head>` in `src/openclaw_gateway/static/dashboard.html`
- [ ] T043 Update `tests/unit/test_dashboard_html.py` to assert that the HTML file contains all required landmark IDs: `status-panel`, `cycles-panel`, `deals-panel`, `quota-panel`, `run-cycle-btn`, `offline-banner`, `deal-filter`
- [ ] T044 Run full test suite `pytest` — all 279 existing tests plus new route and HTML tests must pass
- [ ] T045 Manual integration test per `specs/006-web-dashboard/quickstart.md`: start gateway, open `http://127.0.0.1:18790`, verify all 4 panels render with real data, test offline state (kill gateway → reload → banner appears), test Run Cycle button, test deal filter with each of the 6 status values

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion (T001–T003) — **BLOCKS all user story phases**
- **US1 (Phase 3)**: Depends on Phase 2 (T011 — routes registered, T016 — tests green)
- **US2 (Phase 4)**: Depends on Phase 2; can start in parallel with US1 if staffed (different sections of dashboard.html, but shared `refresh()` function modification in T028 requires T023 to be done first)
- **US3 (Phase 5)**: Depends on Phase 2; can start in parallel with US1/US2; T033 depends on T023 (`renderStatus()` must exist)
- **US4 (Phase 6)**: Depends on Phase 2; fully independent of US1–US3
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

| Story | Depends on | Can start after |
|-------|------------|----------------|
| US1 (P1) | Phase 2 complete | T016 |
| US2 (P2) | Phase 2 complete + T023 exists | T023 (for refresh() shared state) |
| US3 (P3) | Phase 2 complete + T021 exists | T021 (for renderStatus + cycle_running) |
| US4 (P4) | Phase 2 complete | T016 |

### Within Each User Story

- HTML structure task before JS render function task (structure defines element IDs)
- Render function before wiring into `refresh()` (function must exist before being called)
- All CSS tasks are parallelizable with other tasks in the same phase (separate CSS rules)

### Parallel Opportunities

- T002, T003 can run in parallel with T001 (different files)
- T005–T010 can all run in parallel (same file `api.py`, but separate functions — coordinate if single implementer)
- T012, T013, T014 can run in parallel (separate test functions, same test file)
- T041, T042 in Phase 7 can run in parallel with T039, T040

---

## Parallel Example: Phase 2 (Foundational)

```
# Once T001-T003 (Phase 1) are done, launch in parallel:
Task A: T005 — serve_dashboard handler (api.py)
Task B: T006 — api_status handler (api.py)
Task C: T007 — api_cycles handler (api.py)
Task D: T008 — api_deals handler (api.py)
Task E: T009 — api_quota handler (api.py)
Task F: T010 — api_run_cycle handler (api.py)

# Then sequentially:
T011 — register routes in server.py
T012, T013, T014 — unit tests (can run in parallel)
T015 — HTML smoke test
T016 — full pytest run
```

---

## Implementation Strategy

### MVP First (US1 Only — phases 1–3)

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundational) → gateway serves placeholder page + REST endpoints
3. Complete Phase 3 (US1) → status panel + cycles panel working
4. **STOP and VALIDATE**: Start gateway, open dashboard — health badge + uptime + component grid + cycles table visible with real data
5. Confirm 279 + new tests pass
6. This is the minimum dashboard that delivers the most critical operator need (SC-001)

### Incremental Delivery

1. **MVP** (Phase 1–3): Status panel + cycles panel (US1)
2. **+Deals** (Phase 4): Deal filtering and records (US2)
3. **+Trigger** (Phase 5): Run Cycle button (US3)
4. **+Quota** (Phase 6): Gemini quota panel (US4)
5. **Polish** (Phase 7): Auto-refresh, offline state, theming — ship

Each increment is independently useful and does not break previous increments.

---

## Task Count Summary

| Phase | Tasks | Notes |
|-------|-------|-------|
| Phase 1 — Setup | 3 | T001–T003 |
| Phase 2 — Foundational | 13 | T004–T016 |
| Phase 3 — US1 (P1) | 8 | T017–T024 |
| Phase 4 — US2 (P2) | 5 | T025–T029 |
| Phase 5 — US3 (P3) | 5 | T030–T034 |
| Phase 6 — US4 (P4) | 4 | T035–T038 |
| Phase 7 — Polish | 7 | T039–T045 |
| **Total** | **45** | |

---

## Notes

- `[P]` tasks operate on different files or non-conflicting sections — safe to parallelize
- `[Story]` label maps each task to its user story for traceability to spec.md
- All dashboard.html changes are in one file — single implementer can work sequentially; two implementers should coordinate on shared functions (`refresh()`, CSS variables)
- Commit after each phase checkpoint (or each logical group of tasks)
- Stop at any phase checkpoint to validate independently before continuing
- FR-023: Do NOT reference Claude Code, Claude, or Anthropic in any delivered `src/` or `static/` file
