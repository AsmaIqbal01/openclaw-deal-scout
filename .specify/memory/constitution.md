<!--
SYNC IMPACT REPORT
==================
Version change: (none — initial constitution) → 1.0.0
Modified principles: N/A (first authoring)
Added sections:
  - Core Principles (6 principles)
  - Technology Stack & Architecture
  - Development Workflow & Quality Gates
  - Governance
Removed sections: N/A (replacing blank template)
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check gates derived from principles below
  ✅ .specify/templates/spec-template.md — no structural changes needed; FR/SC patterns align
  ✅ .specify/templates/tasks-template.md — task phases align with headless, idempotency, and error-handling principles
  ✅ .claude/commands/*.md — generic agent references; no outdated agent-specific names found
Deferred TODOs:
  - RATIFICATION_DATE set to 2026-07-08 (project creation date; adjust if earlier decision existed)
  - HubSpot free-tier quota numbers (100 req/10 sec) are operator-confirmed; re-verify on HubSpot changelog
-->

# OpenClaw Deal Scout Constitution

## Core Principles

### I. Zero Cost Infrastructure (NON-NEGOTIABLE)

Every component of the pipeline — intake, orchestration, LLM inference, CRM, and
notifications — MUST run on free tiers or self-hosted services with zero recurring
monetary cost to the operator.

- Paid APIs, paid hosting, and paid notification channels are PROHIBITED, including
  in development and staging environments.
- Free-tier limits (e.g., Gemini 2.5 Flash quotas, HubSpot Free CRM API caps,
  Discord rate limits) define the performance envelope; design MUST stay within them.
- Any proposed dependency MUST be vetted for cost before adoption. A dependency that
  requires a credit card even for a free tier MUST be replaced or removed.
- Self-hosting on the operator's machine (via systemd) is the canonical deployment
  model; no cloud infrastructure bill is acceptable.

**Rationale**: OpenClaw Deal Scout serves Pakistani SMBs and freelancers for whom
infrastructure cost is a direct barrier to adoption. The zero-cost constraint is a
product promise, not an optimization goal.

### II. Gmail-Only Intake (MVP NON-NEGOTIABLE)

In this version, Gmail is the sole inbound deal-signal source.

- The pipeline MUST NOT include web scraping, RSS polling, webhook listeners, or any
  intake channel other than the Gmail API.
- The Gmail connection MUST use OAuth with a refreshable offline token stored as a
  credential file; it MUST NOT require a browser login at runtime (see Principle III).
- Gmail polling interval is the only supported trigger mechanism for MVP.
- Expanding intake sources is an explicit out-of-scope item; any proposal to add a
  second source MUST go through a constitution amendment and a new feature spec.

**Rationale**: Scope discipline prevents scope creep. One working intake channel
delivered reliably is more valuable than three half-working ones.

### III. Headless / Unattended Operation (NON-NEGOTIABLE)

No step in the automated pipeline MAY require a human to perform a manual browser
action, interactive login, or runtime approval.

- OAuth tokens MUST use offline access + refresh tokens. Token refresh MUST happen
  programmatically without user intervention.
- MCP servers and external integrations (HubSpot Service Key, Discord bot/
  webhook) MUST authenticate via static credentials or non-interactive tokens only.
- The OpenClaw agent MUST run as a systemd service that survives reboots without
  operator input.
- Any dependency that mandates browser-based OAuth at runtime (e.g., the official
  HubSpot MCP requiring OAuth login) is PROHIBITED for use in the runtime path.

**Rationale**: The product promise is 24/7 automated operation. Any human-in-the-loop
runtime step breaks that promise and defeats the Digital FTE value proposition.

### IV. State-Driven Idempotency

Every deal processed by the pipeline MUST be tracked by its Gmail message ID in a
persistent state store to prevent duplicate CRM entries and duplicate notifications.

- Before logging a deal to HubSpot or sending a Discord alert, the agent MUST check
  whether that Gmail message ID has already been processed.
- The state store MUST persist across agent restarts (file-based JSON or SQLite are
  acceptable; in-memory state is PROHIBITED).
- A deal MUST be marked as processed only AFTER both the CRM entry and the
  notification have succeeded (or have been intentionally skipped per error policy).
- Re-processing MUST be possible by deleting or editing the state entry for a given
  message ID — no hard-coded locks.

**Rationale**: Duplicate CRM contacts and duplicate Discord pings erode operator
trust immediately. Idempotency is non-negotiable in any pipeline that retries.

### V. Modular Notification Architecture

The notification target (currently Discord #deal_alerts) MUST be swappable to any
other channel (Slack, Email, SMS) by changing a single configuration block, without
modifying deal-detection logic or CRM-logging logic.

- Notification logic MUST live in a dedicated notifier module/adapter with a
  documented interface (e.g., `notify(deal: DealPayload): Promise<void>`).
- The active notifier MUST be selected via a configuration key (e.g.,
  `NOTIFIER=discord|slack|email|sms`), not via code branching in core pipeline files.
- Each notifier adapter is independently testable in isolation.
- Adding a new notifier MUST NOT require changes to `deal-detector`, `crm-logger`,
  or orchestrator pipeline files.

**Rationale**: Discord is the MVP output. The modular contract ensures the product
can serve operators on different platforms without a refactor.

### VI. Graceful Degradation & Error Resilience

The agent MUST NEVER crash due to a recoverable external failure. Each failure mode
has a defined response:

| Failure | Behavior |
|---|---|
| Gemini API rate limit (429) | Exponential back-off (max 3 retries, 60 s cap); skip email and log `[WARN] LLM rate-limited` if retries exhausted |
| Discord webhook / API failure | Log `[WARN] Notifier failed`; mark deal state as `crm-logged-notify-pending`; retry on next poll cycle |
| HubSpot rate limit (100 req/10 s) | Queue remaining CRM writes; drain queue with 100 ms delay between requests; log each queued write |
| Gmail OAuth token expiry | Trigger programmatic token refresh; if refresh fails, log `[ERROR] Gmail token refresh failed` and pause polling; alert operator via fallback log file |

- Unhandled exceptions MUST be caught at the pipeline boundary, logged with full
  stack trace, and MUST NOT terminate the systemd service process.
- All errors MUST be written to a rotating log file accessible without agent restart.
- "Skip and log" is always preferable to crashing.

**Rationale**: An unattended agent that crashes silently provides no value. Defined
fallback behavior means the operator can diagnose issues from logs without being
paged at 3 AM.

## Technology Stack & Architecture

This section documents the live, running architecture. Do not invent alternatives;
update this section when the architecture changes via a constitution amendment.

| Layer | Component | Notes |
|---|---|---|
| Orchestrator | OpenClaw (Node.js agent gateway) | Self-hosted via systemd on operator machine |
| Intake | Gmail API | OAuth offline token; testing-mode OAuth app |
| LLM | Google Gemini 2.5 Flash | Free tier; OpenClaw default model |
| CRM | HubSpot Free CRM | Accessed via Service Key MCP server |
| Notification | Discord #deal_alerts | Native OpenClaw channel; bot/webhook auth |
| State Store | File-based (JSON/SQLite) | Keyed by Gmail message ID; persists across restarts |

**Constitution Check Gates** (enforced in plan.md and code review):

- [ ] Does this change introduce any paid dependency?
- [ ] Does this change add a non-Gmail intake source to the MVP pipeline?
- [ ] Does this change require a runtime browser login?
- [ ] Does this change risk duplicate CRM entries or duplicate alerts?
- [ ] Does this change modify core pipeline files to add a new notification target
      instead of adding a new notifier adapter?
- [ ] Does this change allow an exception to crash the agent process?

Any "Yes" answer is a constitution violation and MUST be resolved before merge.

## Development Workflow & Quality Gates

- **Smallest viable diff**: PRs MUST contain only changes required by the current
  task. Unrelated refactors are PROHIBITED in the same commit.
- **No secrets in code**: Gmail credentials, HubSpot private-app-token, Discord
  webhook URL MUST be stored in `.env` and MUST NOT appear in committed files.
  `.env` MUST be listed in `.gitignore`.
- **Explicit error paths**: Every external call (Gmail, Gemini, HubSpot, Discord)
  MUST have an explicit error handler consistent with the Graceful Degradation
  principle (Principle VI).
- **Config over code for notifiers**: Notification target selection via environment
  variable; no `if DISCORD ... else if SLACK` blocks in pipeline code.
- **Log verbosity levels**: DEBUG (polling start/end), INFO (deal detected, CRM
  logged, notified), WARN (retries, skips), ERROR (unrecoverable, operator action
  needed).
- **PHR on every prompt**: All AI-assisted development sessions MUST produce a
  Prompt History Record filed under `history/prompts/`.

## Governance

This constitution supersedes all other development practices, inline comments,
and README guidance where they conflict.

**Amendment procedure**:
1. Propose the amendment in a feature spec or ADR (`/sp.adr <title>`).
2. Obtain explicit operator approval before implementing.
3. Update this file, bump the version (MAJOR/MINOR/PATCH per semantic rules below),
   and update `LAST_AMENDED_DATE`.
4. Propagate changes to dependent templates (plan, spec, tasks) in the same commit.

**Versioning policy**:
- MAJOR: Removal or redefinition of a non-negotiable principle (I, II, III).
- MINOR: Addition of a new principle or material expansion of an existing one.
- PATCH: Wording clarifications, typo fixes, table updates, non-semantic changes.

**Compliance review**: Every PR review MUST verify the Constitution Check Gates
in the Technology Stack section. Failing gates block merge.

**Runtime guidance**: See `CLAUDE.md` for agent-specific development guidance and
tool usage conventions.

**Version**: 1.0.1 | **Ratified**: 2026-07-08 | **Last Amended**: 2026-07-09
