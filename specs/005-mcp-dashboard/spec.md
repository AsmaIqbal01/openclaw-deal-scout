# Feature Specification: OpenClaw MCP Gateway + Dashboard

**Feature Branch**: `005-mcp-dashboard`
**Created**: 2026-07-23
**Status**: Draft
**Input**: User description: "## Feature: OpenClaw proper MCP orchestrator + dashboard (Option B rebuild) — OpenClaw Deal Scout is a 4-step AI pipeline (Gmail → Gemini → HubSpot → Discord) that is currently LIVE in production via systemd timer. All business logic exists and is test/output contracts."

---

## Overview

OpenClaw Deal Scout's 4-step pipeline (Gmail intake → Gemini classification → HubSpot CRM → Discord notification) runs successfully on a systemd timer. What is missing is an operator-facing control plane: a way to check system health at a glance, view recent deals, monitor quota usage, and trigger a manual run — without SSH-ing into logs.

OpenClaw ships a built-in web dashboard at `http://127.0.0.1:18789`. This feature wires the pipeline into that existing dashboard by exposing pipeline state, deal records, quota usage, and a run-trigger as MCP tools that the OpenClaw gateway serves. **No custom dashboard UI is built from scratch.** The implementation is: MCP tools expose data → OpenClaw gateway serves them → existing dashboard at port 18789 displays them.

The feature also delivers a minimal `openclaw` CLI with three subcommands: `gateway status`, `dashboard` (opens the browser UI), and `doctor` (health check).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Instant Health Check via CLI (Priority: P1)

The operator wants to know whether the pipeline is alive without opening a browser. They run `openclaw doctor` from any terminal on the host machine and get a per-component pass/fail report in under 10 seconds.

**Why this priority**: This is the fastest confidence check and the most likely command to run after a reboot, a credential rotation, or a suspected quota suspension. It has no UI dependencies and can be delivered standalone.

**Independent Test**: Run `openclaw doctor` on a healthy machine → all components show PASS. Simulate a bad credential → the affected component shows FAIL with a clear message. No browser or running gateway required.

**Acceptance Scenarios**:

1. **Given** all credentials and env vars are valid and all external services are reachable, **When** the operator runs `openclaw doctor`, **Then** each component (Gmail OAuth, Gemini API key, HubSpot token, Discord webhook, state store) is listed as PASS and the overall result is HEALTHY.
2. **Given** the Gmail OAuth token has expired and cannot be refreshed, **When** the operator runs `openclaw doctor`, **Then** the Gmail component shows FAIL with a human-readable reason, the other components are still evaluated, and the overall result is DEGRADED.
3. **Given** the state store file is missing, **When** the operator runs `openclaw doctor`, **Then** the state store component shows FAIL and the command exits with a non-zero code so scripts can detect the failure.

---

### User Story 2 — Gateway Status Check (Priority: P2)

The operator wants to know whether the OpenClaw gateway service (the MCP orchestrator process) is currently running. They run `openclaw gateway status` and get a one-line answer: running or stopped, with uptime if running.

**Why this priority**: Before using the dashboard or triggering a manual run, the operator needs to know the gateway is up. This command is a prerequisite signal for other operations.

**Independent Test**: Start the gateway → `openclaw gateway status` reports RUNNING with uptime. Stop the gateway → `openclaw gateway status` reports STOPPED. No dashboard interaction required.

**Acceptance Scenarios**:

1. **Given** the OpenClaw gateway process is running, **When** the operator runs `openclaw gateway status`, **Then** the output shows RUNNING, the process uptime, and the gateway version, and the command exits with code 0.
2. **Given** the OpenClaw gateway process is not running, **When** the operator runs `openclaw gateway status`, **Then** the output shows STOPPED and the command exits with a non-zero code.
3. **Given** the gateway is running but has not completed a pipeline cycle yet, **When** the operator runs `openclaw gateway status`, **Then** the output shows RUNNING with last-cycle time as "never".

---

### User Story 3 — Dashboard: Pipeline Status & Deal History (Priority: P3)

The operator opens the dashboard in their browser and immediately sees the current pipeline state, the deals extracted in recent cycles, and the Gemini quota remaining for the day.

**Why this priority**: The CLI commands cover reactive health checks; the dashboard adds a persistent ambient view of the pipeline's output and health — useful for showing stakeholders what the system captured without log diving.

**Independent Test**: With the gateway running and at least one completed cycle, open the dashboard → see last-cycle status, deal count, quota usage bar, and a deal table with at least one row.

**Acceptance Scenarios**:

1. **Given** the gateway has completed at least one pipeline cycle, **When** the operator opens the dashboard, **Then** they see: pipeline state (idle/running/error), last cycle timestamp, total deals extracted today, Gemini quota used/remaining, and a table of recent deals with sender, subject, HubSpot deal ID, and notification status.
2. **Given** the pipeline is mid-cycle (currently running), **When** the operator views the dashboard, **Then** the pipeline state indicator shows RUNNING and auto-updates when the cycle completes without requiring a page refresh.
3. **Given** a cycle completed with errors (e.g., CRM suspension), **When** the operator views the dashboard, **Then** the error tokens from that cycle are visible alongside the cycle summary row.

---

### User Story 4 — Dashboard: Manual Pipeline Trigger (Priority: P4)

The operator wants to run the pipeline immediately without waiting for the next systemd timer tick. They click "Run Now" on the dashboard, see the cycle in progress, and see the results when it finishes.

**Why this priority**: The timer-based scheduling works for unattended production. The manual trigger is needed for testing, demos, and "I just got an important email" scenarios.

**Independent Test**: Click "Run Now" → loading state appears → cycle completes → result (deals found, quota used) is shown without page refresh.

**Acceptance Scenarios**:

1. **Given** the gateway is running and no cycle is currently active, **When** the operator clicks "Run Now", **Then** the dashboard enters a loading state, the pipeline executes one full cycle, and results are displayed when complete.
2. **Given** a cycle is already running, **When** the operator clicks "Run Now", **Then** the button is disabled and a "Cycle in progress" message is shown — no duplicate cycle is triggered.
3. **Given** a manual cycle fails with an error, **When** the cycle completes, **Then** the error is displayed in the dashboard and the "Run Now" button becomes active again.

---

### User Story 5 — Production Code Independence from Developer Tooling (Priority: P1)

A code audit of all production pipeline modules (gmail_intake, crm_logger, discord_notifier, pipeline_orchestrator, and the new MCP gateway) finds zero references to Claude Code, the Claude Code CLI, or any Anthropic developer tooling.

**Why this priority**: Production code that requires a developer tool to run is fragile. The pipeline must be independently deployable on any Ubuntu server without Claude Code installed.

**Independent Test**: Run a grep audit of all `src/` modules for Claude Code references → zero matches. Uninstall Claude Code from the machine → the pipeline, gateway, and CLI all continue to function normally.

**Acceptance Scenarios**:

1. **Given** the complete `src/` directory and any new gateway/CLI source, **When** an automated scan checks for Claude Code references (package imports, CLI invocations, API key usage, environment variables specific to Claude Code), **Then** zero matches are found.
2. **Given** Claude Code is not installed on the host, **When** the operator starts the gateway and runs the pipeline, **Then** the pipeline completes normally and all steps succeed.

---

### Edge Cases

- What happens when `openclaw doctor` is run while the gateway is stopped? — The doctor command evaluates credentials and external services independently of the gateway; it does not require the gateway to be running.
- What happens if the dashboard is opened before any cycle has completed? — Dashboard shows "No cycles yet" with an empty deal table and a "Run Now" button as the only action.
- What happens if Gemini quota is fully exhausted when the operator clicks "Run Now"? — The cycle runs the FR-022 path: step 1 exits with `RateLimitExhaustedError`, steps 2 and 3 drain pending entries. The dashboard shows the `quota_exhausted` error token in the cycle result.
- What happens when the gateway receives a `Run Now` request while already running a cycle? — Request is rejected with a "cycle in progress" response; the dashboard reflects this without triggering a second cycle.
- What happens if the gateway process crashes between dashboard refreshes? — The dashboard detects the gateway as unreachable and shows a GATEWAY OFFLINE state; the "Run Now" button is disabled.

---

## Requirements *(mandatory)*

### Functional Requirements

**Gateway (MCP Orchestrator)**

- **FR-001**: The system MUST provide a standalone OpenClaw gateway service that orchestrates the 4-step pipeline (Gmail → Gemini → HubSpot → Discord) via the MCP protocol without relying on any developer tooling at runtime.
- **FR-002**: The gateway MUST support being started and stopped independently of the dashboard and the `openclaw` CLI.
- **FR-003**: The gateway MUST expose a `run_cycle` operation that executes one complete pipeline cycle and returns a cycle summary.
- **FR-004**: The gateway MUST enforce the existing cycle-lock semantics: if a cycle is already running, a second `run_cycle` request MUST be rejected with a "busy" response.
- **FR-005**: The gateway MUST maintain the existing dual-mode scheduler support: unattended scheduling via systemd timer and a sleep-loop mode for development.
- **FR-006**: The gateway MUST emit a rotating cycle-summary log (same format as the current `pipeline.log`) on every cycle completion, regardless of outcome.
- **FR-007**: The gateway MUST handle SIGTERM gracefully: complete the current step, release the cycle lock, and exit with code 0.
- **FR-008**: All production source files (`src/`) MUST contain zero references to Claude Code, the Claude Code CLI, or any Anthropic developer SDK used only in development tooling.

**CLI: `openclaw` command**

- **FR-009**: The system MUST provide an `openclaw` CLI command installable on the host machine without Claude Code.
- **FR-010**: `openclaw gateway status` MUST report whether the gateway process is running on port 18789, its uptime, the gateway version, and the timestamp of the last completed cycle. Exit code 0 if running, non-zero if stopped.
- **FR-010a**: `openclaw dashboard` MUST open the operator's default browser to `http://127.0.0.1:18789`. If the gateway is not running, the command MUST print a clear message and exit with a non-zero code rather than opening a blank page.
- **FR-011**: `openclaw doctor` MUST check and report pass/fail for each of the following components: Gmail OAuth credentials, Gemini API key, HubSpot service token, Discord webhook, and the state store file. Exit code 0 if all pass, non-zero if any fail.
- **FR-012**: `openclaw doctor` MUST test reachability of each external service (not just credential presence) and report the result per service.

**Dashboard (OpenClaw built-in at port 18789)**

- **FR-013**: The system MUST use OpenClaw's existing built-in dashboard served at `http://127.0.0.1:18789`. The gateway bind address MUST default to `127.0.0.1` (localhost-only). An environment variable MUST allow the operator to override the bind address (e.g., `0.0.0.0` for LAN access) without code changes. A custom dashboard UI MUST NOT be built from scratch.

- **FR-014**: The dashboard MUST display the current pipeline state (idle, running, or error) and update the display when the state changes, without requiring a manual page refresh.
- **FR-015**: The dashboard MUST display a Gemini quota usage indicator showing estimated requests used vs. the daily free-tier limit.
- **FR-016**: The dashboard MUST display a table of deals extracted, showing at minimum: sender name, email subject, deal type, confidence score, HubSpot deal ID (if logged), and Discord notification status.
- **FR-017**: The dashboard MUST display a list of recent pipeline cycle summaries, including timestamp, emails processed, deals found, CRM logged, notified, pending, and error tokens.
- **FR-018**: The dashboard MUST provide a "Run Now" button that triggers one pipeline cycle immediately via the gateway. The button MUST be disabled while a cycle is in progress.
- **FR-019**: The dashboard MUST show an error message and disable the "Run Now" button when the gateway is offline.

**Regression gate**

- **FR-020**: All existing unit and integration tests (currently 222+ passing) MUST continue to pass after this feature is implemented. No existing test contract may be removed or modified to accommodate this rebuild.

### Key Entities

- **GatewayStatus**: The runtime state of the OpenClaw gateway process — whether it is running or stopped, its uptime, version string, and the timestamp of the most recent completed cycle.
- **PipelineCycle**: A completed or in-progress pipeline run — timestamp, duration, emails processed, deals extracted, CRM entries logged, Discord notifications sent, pending entries count, and a list of error tokens.
- **DealRecord**: A deal captured from the inbox — Gmail message ID, sender name, sender email, subject, deal type classification, confidence score, HubSpot deal ID, CRM log status, and notification status.
- **QuotaUsage**: Estimated Gemini API consumption — requests used in the current rolling window, estimated daily total, and remaining budget against the free-tier limit.
- **HealthCheckReport**: A per-component diagnostic — one entry per service (Gmail, Gemini, HubSpot, Discord, state store), each with a pass/fail status, latency (for network checks), and a human-readable message on failure.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The operator can determine the full health of the pipeline (all 5 components) in under 10 seconds by running a single command on the host machine.
- **SC-002**: The operator can view the current pipeline state, today's deal count, and Gemini quota remaining within 2 seconds of opening the dashboard in a browser.
- **SC-003**: `openclaw gateway status` responds with RUNNING/STOPPED within 1 second and accurately reflects the gateway process state.
- **SC-004**: A "Run Now" action from the dashboard triggers a full pipeline cycle and displays the cycle result without requiring the operator to leave the browser or refresh the page.
- **SC-005**: All 222+ existing unit and integration tests pass without modification after the rebuild is complete.
- **SC-006**: An automated scan of all production source files (`src/`) returns zero matches for Claude Code references.
- **SC-007**: The gateway, dashboard, and `openclaw` CLI all function correctly on a machine where Claude Code is not installed.

---

## Scope

### In Scope

- A standalone OpenClaw gateway service implementing the MCP protocol to orchestrate the existing 4-step pipeline, serving on port 18789.
- MCP tools that expose pipeline state, deal records, quota usage, and a run-trigger to OpenClaw's built-in dashboard.
- An `openclaw` CLI providing `gateway status`, `dashboard`, and `doctor` subcommands.
- Removal of all Claude Code references from production source files.

### Out of Scope

- Building a custom dashboard UI from scratch (OpenClaw's built-in dashboard at port 18789 is used as-is).
- Changing any of the existing pipeline step logic (gmail_intake, crm_logger, discord_notifier, pipeline_orchestrator).
- Authentication or access control for the dashboard (single-operator, local-only deployment assumed).
- Modifying or removing any existing tests.
- Adding a second intake source or a new notification channel.
- Cloud hosting or any paid infrastructure.

---

## Assumptions

- OpenClaw's built-in dashboard is served at `http://127.0.0.1:18789`; the gateway binds to that address by default.
- The `openclaw` CLI does not require Claude Code to be installed; it communicates with the gateway via port 18789.
- Gemini quota tracking is an estimate based on the cycle log (requests counted per cycle, not via a Gemini API quota endpoint), since the free-tier quota API is not available.
- The existing systemd timer and unit files (`deploy/openclaw.service`, `deploy/openclaw.timer`) remain in place; the gateway is the process that systemd manages.
- "Zero references to Claude Code" means: no `import` or dependency on `@anthropic-ai/claude-code`, no `claude` CLI invocations, no `CLAUDE_API_KEY` or similar env vars in pipeline source.
- Three skills are installed before implementation begins: `anthropics/skills/mcp-builder` (MCP tool contracts), `anthropics/skills/webapp-testing` (dashboard tests), `anthropics/skills/frontend-design` (dashboard UI guidance).

---

## Dependencies

- Existing packages: `gmail_intake`, `crm_logger`, `discord_notifier`, `pipeline_orchestrator` — unchanged.
- Existing deploy artifacts: `deploy/openclaw.service`, `deploy/openclaw.timer`, `deploy/README.md` — referenced by the new gateway.
- State store: `processed_ids.json` — read by the MCP tools and `openclaw doctor`.
- Cycle log: `pipeline.log` — read by the MCP tools for cycle history surfaced in the dashboard.
- OpenClaw built-in dashboard — pre-existing UI at port 18789; no custom frontend required.
- Skills (installed before implementation): `anthropics/skills/mcp-builder`, `anthropics/skills/webapp-testing`, `anthropics/skills/frontend-design`.
