# OpenClaw Deal Scout

**Autonomous inbox-to-CRM deal pipeline for solo operators — zero infrastructure, zero monthly bill.**

OpenClaw Deal Scout watches a Gmail inbox, uses an LLM to tell genuine business
inquiries apart from spam and noise, logs confirmed deals straight into a free
HubSpot CRM, pings the operator on Discord, and — when approved — drafts and
sends the reply itself at the right time. It runs as a single local process
(an MCP gateway + web dashboard) with no database, no cloud bill, and no
DevOps: a JSON file is the state store, and the whole thing runs on a free-tier
Gemini API key and free-tier HubSpot/Discord accounts.

## The problem

Two operators, one gap: **email is where deals arrive, and nobody has time to
babysit it.**

- **UK micro-businesses** (fewer than 10 employees) get inbound partnership
  and inquiry emails buried in a noisy inbox alongside spam and newsletters.
  There's no receptionist to triage them and no budget for a full CRM seat.
- **Pakistani SMBs and freelancers** selling into that market face the same
  problem from the other side, plus a harder constraint: **infrastructure
  cost is a direct barrier to adoption.** A paid CRM plan, a hosted database,
  or a cloud bill can be the difference between using a tool and not using it.

OpenClaw Deal Scout is built for that second constraint first: it is a
**zero-cost, single-machine product**, not a hosted SaaS with a free tier.
Every dependency (Gmail, Gemini, HubSpot, Discord) has a free tier that's
enough to run a real small business, and the state store is a JSON file, not
a hosted database.

## How it works

Each pipeline cycle runs the same four steps, orchestrated by
`pipeline_orchestrator` and exposed through an MCP gateway + dashboard:

```
                    ┌───────────────────────────────────────────────────┐
                    │              OpenClaw Gateway (FastMCP)            │
                    │     scheduler thread ticks every N minutes         │
                    └───────────────────────────────────────────────────┘
                                          │
   ┌──────────────┐   1. INTAKE          ▼
   │  Gmail inbox │ ───────────►  ┌──────────────┐
   └──────────────┘               │ Gemini triage │  spam / noise → discarded
                                   │ (deal detect) │
                                   └──────┬───────┘
                                          │ confirmed deal
                                          ▼
                                   ┌──────────────┐   2. CRM LOG
                                   │  HubSpot CRM  │◄──────────────
                                   │ contact+deal  │  (pending + retry
                                   └──────┬───────┘   on failure)
                                          │
                                          ▼
                                   ┌──────────────┐   3. NOTIFY
                                   │   Discord     │◄──────────────
                                   │  webhook ping │
                                   └──────┬───────┘
                                          │ operator approves reply
                                          ▼
                                   ┌──────────────┐   4. SCHEDULE + SEND
                                   │ email_queue   │  waits for UK business
                                   │ .json (state) │  hours (Mon–Fri 09–17
                                   └──────┬───────┘  Europe/London), retries
                                          │           failed sends 3x
                                          ▼
                                   ┌──────────────┐
                                   │  Gmail API    │  reply sent
                                   │  send         │
                                   └──────────────┘

              ┌─────────────────────────────────────────────┐
              │   Web Dashboard  ◄── REST ──►  Gateway state  │
              │   (deals, cycles, quota, pending approvals)   │
              └─────────────────────────────────────────────┘
```

Every step is failure-isolated: a Gmail quota exhaustion, a HubSpot outage, or
a Discord webhook error degrades that one step to a `pending` state with
retry/backoff — it never aborts the whole cycle (see ADR-0003, ADR-0009).

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ (3.12 for orchestration/gateway) | single runtime, no polyglot ops |
| Agent protocol | FastMCP (HTTP transport) | first-class MCP tool + custom REST routes in one server |
| Deal classification | Gemini API (free tier) | no self-hosted model, no GPU |
| CRM | HubSpot Free CRM (Private App token) | zero-cost CRM with a real API |
| Notifications | Discord webhook | zero-cost, operator already has Discord |
| Outbound email | Gmail API (send), not raw SMTP | reuses existing OAuth grant (ADR-0008) |
| State store | Single JSON file (`processed_ids.json`, `email_queue.json`) | zero infrastructure, human-readable, survives reboots without a daemon (ADR-0002) |
| Dashboard | Zero-build single HTML file, vanilla JS/CSS | no bundler, no node_modules in production (ADR-0007) |
| Scheduling | In-process background thread, single process | no external cron/queue service (ADR-0005) |
| Tests | pytest + pytest-asyncio | unit + integration, run offline |

## How to run locally

**Prerequisites:** Python 3.11+, a Gmail account, a free Gemini API key, a free
HubSpot account, and a Discord server you can add a webhook to.

```bash
# 1. Clone and install
git clone https://github.com/AsmaIqbal01/openclaw-deal-scout.git
cd openclaw-deal-scout
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configure credentials
cp .env.example .env
# Fill in: GMAIL_CREDENTIALS_PATH, GEMINI_API_KEY, HUBSPOT_PRIVATE_APP_TOKEN,
#          NOTIFIER=discord, DISCORD_WEBHOOK_URL

# 3. Run the test suite (should be all green before you touch config)
pytest -q

# 4. Start the gateway (dashboard + scheduler + MCP tools)
python -m openclaw_gateway
# Gateway listens on http://127.0.0.1:18790 by default (GATEWAY_HOST/GATEWAY_PORT to override)

# 5. Open the dashboard
openclaw dashboard
# or check status/health from the CLI:
openclaw gateway status
openclaw doctor
```

The scheduler thread runs pipeline cycles automatically; `get_pipeline_cycles`
and `get_deals` (exposed as MCP tools and dashboard REST endpoints) let you
inspect what happened without touching the JSON files directly.

## Test suite

**482 passing, 9 skipped, 498 total** — unit + integration coverage across
Gmail intake, deal classification, HubSpot sync, Discord notification,
pipeline orchestration, the MCP gateway/dashboard, and email scheduling.

```bash
pytest -q
```

## Project status

**7 features shipped, running in production for real operator inboxes:**

| # | Feature | Status |
|---|---|---|
| 001 | Gmail intake & deal detection | ✅ shipped |
| 002 | HubSpot CRM logger | ✅ shipped |
| 003 | Discord deal notification | ✅ shipped |
| 004 | Pipeline orchestration & error handling | ✅ shipped |
| 005 | MCP gateway + dashboard (backend) | ✅ shipped |
| 006 | Web dashboard (UI) | ✅ shipped |
| 007 | Email scheduling & smart send-time | ✅ shipped |

Each feature followed spec → plan → tasks → implementation, with an
Architecture Decision Record for every cross-cutting design call.

## Architecture Decision Records

Full design rationale lives in [`history/adr/`](history/adr/):

- [ADR-0001](history/adr/0001-python-fastmcp-subprocess-runtime.md) — Python FastMCP subprocess runtime
- [ADR-0002](history/adr/0002-json-file-state-store-mechanism.md) — JSON file state store mechanism
- [ADR-0003](history/adr/0003-crm-write-failable-pending-and-circuit-breaker.md) — CRM write failable-pending state & circuit breaker
- [ADR-0004](history/adr/0004-gateway-http-transport-replaces-stdio-subprocess-model.md) — Gateway HTTP transport replaces stdio subprocess model
- [ADR-0005](history/adr/0005-gateway-scheduler-architecture-single-process-thread-model.md) — Gateway scheduler architecture: single-process thread model
- [ADR-0006](history/adr/0006-browser-to-gateway-rest-adapter-pattern.md) — Browser-to-gateway REST adapter pattern
- [ADR-0007](history/adr/0007-zero-build-single-file-dashboard-strategy.md) — Zero-build single-file dashboard strategy
- [ADR-0008](history/adr/0008-gmail-api-send-vs-raw-smtp-for-outbound-email.md) — Gmail API send vs. raw SMTP for outbound email
- [ADR-0009](history/adr/0009-email-dispatch-threading-model-in-process-synchronous-dispatch.md) — Email dispatch threading model: in-process synchronous dispatch

## License

Proprietary — all rights reserved unless a license file states otherwise.
