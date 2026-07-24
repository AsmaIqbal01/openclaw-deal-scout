# Feature Specification: Web Dashboard for OpenClaw Deal Scout

**Feature Branch**: `006-web-dashboard`
**Created**: 2026-07-24
**Status**: Draft

---

## Overview

OpenClaw Deal Scout is a live AI pipeline that monitors a Gmail inbox and automatically extracts business opportunities, logs them to HubSpot CRM, and sends Discord alerts. The pipeline runs unattended — but today there is no way to see what it has done, whether it is healthy, or trigger a manual run without accessing the server directly.

This feature adds a browser-accessible dashboard served at the gateway URL (`http://127.0.0.1:18790`). The operator opens it with the existing `openclaw dashboard` command and sees pipeline health, detected deals, quota consumption, and recent activity — without touching the server or reading log files.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Pipeline Status at a Glance (Priority: P1)

Asma opens the dashboard after a weekend away and immediately needs to know: is the pipeline healthy, when did it last run, and did anything go wrong? She should not have to open a terminal or grep a log file to get this answer.

**Why this priority**: A broken pipeline means missed deals. The operator must be able to assess pipeline health in under five seconds. Everything else is secondary to this.

**Independent Test**: Open the dashboard with the gateway running. The status panel must display: overall health (HEALTHY or DEGRADED), uptime since gateway start, timestamp of last completed cycle, whether a cycle is currently running, and a component-level health breakdown (Gmail, Gemini, HubSpot, Discord, state store, log). Passes if all six components are visible and reflect real pipeline state.

**Acceptance Scenarios**:

1. **Given** the gateway is running and the pipeline has completed at least one cycle, **When** the operator opens the dashboard, **Then** they see a clearly labelled status of HEALTHY or DEGRADED, uptime in human-readable format (e.g. "2h 14m"), and the exact time of the last completed cycle.
2. **Given** a pipeline cycle is actively running, **When** the operator views the dashboard, **Then** a visible "cycle running" indicator appears and the Run Cycle button is disabled for the duration.
3. **Given** one or more pipeline components are unreachable (e.g. Discord webhook down), **When** the operator views the dashboard, **Then** the overall status shows DEGRADED and the failing component is highlighted by name.
4. **Given** the dashboard has been open for 60 seconds without manual interaction, **When** the auto-refresh fires, **Then** all panels update silently in place without a full page reload.

---

### User Story 2 — Deal Records and Status Filtering (Priority: P2)

Asma wants to review which deals were extracted this week and check whether any are stuck in a pending state (e.g. HubSpot failed to log them). She needs to filter the deal list by status without having to open the raw state file.

**Why this priority**: The deals list is the business output of the pipeline. Seeing which deals are complete vs. stuck is the primary operational task after confirming health.

**Independent Test**: With at least three deals in the state store (spanning different statuses), open the dashboard and use the status filter. Confirm the count and entries change when switching between "all", "crm_pending", "crm_failed", "notify_pending", "notify_failed", and "complete". Passes if each filter returns only matching records.

**Acceptance Scenarios**:

1. **Given** the state store contains deals with mixed statuses, **When** the operator selects a status filter, **Then** only deals matching that status are shown and a count reflects the filtered total.
2. **Given** more deals exist than fit on screen, **When** the operator scrolls or pages through the list, **Then** they can reach all records without the page breaking.
3. **Given** no deals match the active filter, **When** the filter is applied, **Then** a clear "no deals found" message is shown rather than a blank panel.
4. **Given** each deal entry, **When** the operator reads it, **Then** they can see: sender, subject or deal summary, CRM status, notification status, and timestamp — without clicking into a detail view.

---

### User Story 3 — Manual Pipeline Trigger (Priority: P3)

Asma has just onboarded a new email address that sent a deal she wants processed immediately. She clicks "Run Cycle" from the dashboard rather than SSHing into the server to invoke the CLI.

**Why this priority**: Manual trigger is a control capability that builds confidence and reduces operational friction. It is useful but not needed for the dashboard to deliver core value (P1 and P2 cover that).

**Independent Test**: With the gateway running, click "Run Cycle". Confirm: (a) the button shows a loading state and cannot be clicked again, (b) a result appears within 30 seconds showing emails processed, CRM logged, notified, and any errors, (c) the pipeline status panel refreshes after the cycle completes.

**Acceptance Scenarios**:

1. **Given** no cycle is running, **When** the operator clicks "Run Cycle", **Then** the button enters a loading/disabled state immediately and a progress indicator is visible.
2. **Given** a cycle completes successfully, **When** the result is returned, **Then** a summary appears showing counts of emails processed, deals logged to CRM, and notifications sent.
3. **Given** the pipeline is already running when the operator clicks "Run Cycle", **Then** the dashboard returns a "pipeline busy" message rather than starting a second cycle.
4. **Given** a cycle fails with an error, **When** the result is returned, **Then** the error message is displayed in plain language rather than a raw stack trace.

---

### User Story 4 — Gemini Quota Awareness (Priority: P4)

Asma's pipeline uses the Gemini free tier (1 500 requests/day). Near the daily limit, the pipeline silently skips email extraction. She needs to see today's quota usage without inspecting log files.

**Why this priority**: Quota exhaustion is a known operational risk (documented in HEARTBEAT.md). Visibility into it is useful but does not block the core dashboard value — hence P4.

**Independent Test**: With cycles having run today, open the dashboard quota panel. Confirm it shows: requests used today, daily limit (1 500), percentage consumed, and whether a quota error occurred today. Passes if all four values are present and the percentage matches the ratio.

**Acceptance Scenarios**:

1. **Given** cycles have run today, **When** the operator views the quota panel, **Then** they see requests used, the 1 500 daily limit, percentage consumed, and a visual indicator (e.g. progress bar).
2. **Given** a quota exhaustion error occurred today, **When** the operator views the quota panel, **Then** a prominent warning indicates quota was hit and extraction was skipped for affected cycles.
3. **Given** no cycles have run today, **When** the operator views the quota panel, **Then** usage shows zero with the full limit available.

---

### Edge Cases

- What happens when the gateway is not reachable (stopped between page load and refresh)? Dashboard must show a clear "Gateway offline" banner rather than hanging or showing stale data.
- What happens when the state store contains zero deals? Deals panel must show an empty-state message, not a blank white space.
- What happens when `run_cycle` takes longer than 30 seconds? The Run Cycle button must remain disabled; a timeout message must appear after 60 seconds with guidance to check pipeline logs.
- What happens when a cycle is already running when the dashboard loads? The Run Cycle button must load in a disabled state immediately — before the operator has a chance to click it.
- What happens if the pipeline log has no entries yet (fresh install)? Recent cycles panel must show "No cycles recorded yet" rather than an error.

---

## Requirements *(mandatory)*

### Functional Requirements

**Dashboard availability**
- **FR-001**: The dashboard MUST be accessible at the gateway root URL (`http://127.0.0.1:18790`) so that the existing `openclaw dashboard` CLI command opens it without modification.
- **FR-002**: The dashboard MUST load and display data within 3 seconds on a local machine.
- **FR-003**: The dashboard MUST auto-refresh all data panels every 60 seconds without requiring user interaction or a full page reload.
- **FR-004**: The dashboard MUST display a clear "Gateway offline" error state when it cannot reach the pipeline data source, rather than showing stale or empty data silently.

**Pipeline status panel**
- **FR-005**: The dashboard MUST display the current overall pipeline status as either HEALTHY or DEGRADED.
- **FR-006**: The dashboard MUST display gateway uptime in human-readable format (hours and minutes).
- **FR-007**: The dashboard MUST display the timestamp of the last completed pipeline cycle, or "Never" if no cycle has run.
- **FR-008**: The dashboard MUST display a visible indicator when a pipeline cycle is actively running.
- **FR-009**: The dashboard MUST display the health status of each individual pipeline component (Gmail connectivity, Gemini API, HubSpot API, Discord webhook, state store, log file).

**Recent cycles panel**
- **FR-010**: The dashboard MUST display the 20 most recent pipeline cycles in reverse-chronological order.
- **FR-011**: Each cycle entry MUST show: timestamp, number of emails processed, number of deals logged to CRM, number of notifications sent, and any error labels.

**Deals panel**
- **FR-012**: The dashboard MUST display detected deals from the state store, defaulting to the 50 most recent.
- **FR-013**: The dashboard MUST provide a filter control with options: all, crm_pending, crm_failed, notify_pending, notify_failed, complete.
- **FR-014**: Each deal entry MUST display: sender, subject or deal summary, CRM status, notification status, and detected timestamp.
- **FR-015**: The deals panel MUST display a count of total deals matching the active filter alongside the filtered results.

**Quota panel**
- **FR-016**: The dashboard MUST display Gemini quota usage for the current UTC day: requests used, daily limit, percentage consumed, and a visual indicator.
- **FR-017**: The dashboard MUST display a prominent warning when a quota exhaustion error occurred during any cycle today.

**Run Cycle control**
- **FR-018**: The dashboard MUST provide a "Run Cycle" button that triggers an immediate pipeline cycle when clicked.
- **FR-019**: The "Run Cycle" button MUST be disabled and show a loading indicator while a cycle is in progress (whether triggered from the dashboard or running independently).
- **FR-020**: On cycle completion, the dashboard MUST display a result summary (emails processed, CRM logged, notified, errors) before reverting to the idle state.
- **FR-021**: If a cycle is already running when the Run Cycle button is clicked, the dashboard MUST display a "pipeline busy" message rather than starting a second cycle.

**Zero-cost and independence constraints**
- **FR-022**: The dashboard MUST NOT load any resources from external servers (no CDN scripts, no external fonts, no third-party APIs). All assets must be self-contained.
- **FR-023**: The dashboard MUST NOT reference Claude Code or any Anthropic tooling anywhere in the delivered source files.
- **FR-024**: All existing pipeline unit tests (currently 279) MUST continue to pass after this feature is shipped.

### Key Entities

- **Pipeline Status**: Overall health verdict (HEALTHY/DEGRADED), uptime seconds, last cycle timestamp, cycle-running flag, per-component health list.
- **Component Health**: Name (gmail, gemini, hubspot, discord, state_store, log), pass/fail status, optional latency, optional message.
- **Pipeline Cycle**: Timestamp, emails processed, deals logged to CRM, notifications sent, list of error labels.
- **Deal**: Sender, subject/summary, CRM status (pending/logged/failed), notification status (pending/sent/failed), detected timestamp.
- **Quota Usage**: Requests today, daily limit (1 500), percentage used, cycles-today count, quota-error-today flag.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The operator can determine pipeline health status within 5 seconds of opening the dashboard — no terminal access required.
- **SC-002**: The operator can view all detected deals and filter by status within 10 seconds of opening the dashboard.
- **SC-003**: A manually triggered pipeline cycle completes and its result is visible on the dashboard within 30 seconds of clicking "Run Cycle" under normal network conditions.
- **SC-004**: The dashboard accurately reflects a change in pipeline state (new cycle, new deal, quota update) within 60 seconds without a manual page reload.
- **SC-005**: The dashboard loads and is interactive within 3 seconds on a local machine with the gateway running.
- **SC-006**: Zero regressions — all 279 existing unit tests continue to pass after the feature is shipped.
- **SC-007**: The dashboard is fully usable with no internet access (all assets self-contained, zero external requests).

---

## Scope

### In Scope
- Single-page dashboard served at the gateway root, showing pipeline status, recent cycles, deals list, quota usage, and Run Cycle trigger.
- Auto-refresh every 60 seconds.
- Status filter for deals (6 options).
- Run Cycle button with loading state and result display.
- Offline/error state when gateway is unreachable.
- Adding a static file route to the existing gateway server — no new process or port.

### Out of Scope
- User authentication or access control (localhost-only tool).
- Mobile or tablet layout optimisation (desktop browser only).
- Deal detail view or drill-down pages.
- Historical quota charts or trend graphs.
- Email content preview.
- Editing or deleting deals from the dashboard.
- Notifications or browser push alerts.
- Dark/light theme toggle (system preference respected via CSS only).

---

## Dependencies

- **005-mcp-dashboard** (shipped): MCP gateway running at port 18790 with 6 MCP tools.
- **Gateway root route**: Currently returns 404; must be extended to serve the dashboard HTML file.
- **MCP tool contracts** (`specs/005-mcp-dashboard/contracts/mcp-tools.md`): Authoritative schema for all 6 tool responses.

---

## Assumptions

- The dashboard is a localhost-only operator tool — no authentication is required.
- The gateway is already running when the operator opens the dashboard; the dashboard does not start the gateway.
- The 1 500 requests/day Gemini free-tier limit is fixed and does not need to be configurable from the dashboard.
- "Desktop browser" means any modern Chromium, Firefox, or Safari on a 1280px+ screen.
- The `openclaw dashboard` CLI command (already shipped) is the intended launch path; the dashboard URL does not change.
- Deals are displayed newest-first; no sorting controls are required in this version.
