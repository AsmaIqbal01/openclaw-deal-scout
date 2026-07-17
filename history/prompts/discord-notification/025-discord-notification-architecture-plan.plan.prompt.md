---
id: 025
title: Discord Notification Architecture Plan
stage: plan
date: 2026-07-17
surface: agent
model: claude-sonnet-4-6
feature: discord-notification
branch: 003-discord-notification
user: AsmaIqbal000
command: /sp.plan
labels: ["plan","discord-notification","architecture","adapter-pattern","no-new-deps"]
links:
  spec: specs/003-discord-notification/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/003-discord-notification/plan.md
  - specs/003-discord-notification/research.md
  - specs/003-discord-notification/data-model.md
  - specs/003-discord-notification/quickstart.md
  - specs/003-discord-notification/contracts/sync_notifications.tool.md
  - specs/003-discord-notification/contracts/discord_adapter.interface.md
tests:
  - "null (plan phase — no tests written)"
---

## Prompt

/sp.plan

## Response snapshot

Completed full /sp.plan workflow for 003-discord-notification:

**Phase 0 — Research** (research.md):
- Discord rate limit confirmed: 30 req/60 s per webhook (not 5/2 s); 429 body contains `retry_after` float
- Embed limits: title 256 chars, description 4096 chars; HTTP 400 on violation (not silent truncation)
- No idempotency key on webhook POST — state-store check is only safeguard
- `typing.Protocol` chosen over `abc.ABC` for NotifierContract (structural typing, test isolation)
- `timeout=(5, 10)` chosen over `timeout=10` (separate connect/read timeouts)

**Constitution Check**: All 6 gates PASS. Zero new paid dependencies. Zero new Python packages. Webhook URL is static credential.

**Key architectural decisions**:
1. Discord webhook over bot token (simpler, headless, free)
2. `typing.Protocol` for NotifierContract (duck-typed, no base class import in tests)
3. Extend shared `processed_ids.json` (not a new file) with `status`, `notified_at`, `notify_error_reason` fields
4. Drain-first ordering: `crm-logged-notify-pending` before `crm-logged` each cycle
5. No retry counter field; indefinite retry is explicit policy

**New package**: `src/discord_notifier/` — 8 files: `__init__.py`, `models.py`, `adapter.py`, `formatter.py`, `state_store.py`, `notifier.py`, `orchestrator.py`, `server.py`

**Contracts**: `sync_notifications` MCP tool (no params, env-var config), `NotifierContract` Protocol, `DiscordAdapter`, `NoopAdapter`, `get_adapter()` factory

**State transitions added**: `crm-logged` → `discord-notified` | `crm-logged-notify-pending`

## Outcome

- ✅ Impact: Full architecture plan for 003-discord-notification — zero new infrastructure, zero new Python dependencies, backward-compatible state store extension, swappable adapter contract satisfying Principle V
- 🧪 Tests: No tests in plan phase; test contracts defined in contracts/discord_adapter.interface.md (13 test scenarios) and contracts/sync_notifications.tool.md (8 scenarios)
- 📁 Files: 6 new files — plan.md, research.md, data-model.md, quickstart.md, contracts/sync_notifications.tool.md, contracts/discord_adapter.interface.md
- 🔁 Next prompts: `/sp.tasks` to generate the full task breakdown for implementation
- 🧠 Reflection: Research agent confirmed rate limit is 30/60 s (not 5/2 s as initially assumed); HTTP 400 on embed violations means pre-truncation in formatter.py is required; `timeout=(5, 10)` is the correct form for production requests calls

## Evaluation notes (flywheel)

- Failure modes observed: Initial plan.md had incorrect Discord rate limit (5/2 s); corrected after research agent returned
- Graders run and results (PASS/FAIL): Constitution Check — all 6 gates PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Pre-populate research.md skeleton with known Discord API facts (rate limits, embed limits) at spec time to save one research-agent round trip during planning
