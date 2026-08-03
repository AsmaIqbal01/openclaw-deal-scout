# OpenClaw Deal Scout

> AI-powered lead detection pipeline for UK micro-businesses and Pakistani SMBs.

## Status: Production ✅

## Demo
▶️ [Watch live pipeline demo](https://youtube.com/shorts/ZtWuZAr5KUs?si=arSFTtL8kxe2W3Ac)

- 489 tests passing
- 7 features shipped and running
- Pipeline: Gmail → Gemini 2.5 Flash → HubSpot CRM → Discord
- Systemd timer runs automatically every 15 minutes
- Zero infrastructure cost — free tier APIs only

## Live PipelineGmail Intake
↓
Gemini 2.5 Flash (deal classifier)
↓
HubSpot Free CRM (deal logged)
↓
Discord Webhook (agent notified)
↓
Email Queue (operator approval gate)


## Features Shipped

| # | Feature | Status |
|---|---|---|
| 001 | Gmail intake + deal detection | ✅ Production |
| 002 | HubSpot CRM logger | ✅ Production |
| 003 | Discord notifications | ✅ Production |
| 004 | Orchestration + systemd timer | ✅ Production |
| 005 | MCP Gateway (6 tools exposed) | ✅ Production |
| 006 | Vanilla HTML/JS dashboard | ✅ Production |
| 007 | Email scheduling + operator approval | ✅ Production |

## Tech Stack

| Layer | Tech | Why |
|---|---|---|
| Runtime | Python 3.12 | Single runtime, no polyglot ops |
| Agent Protocol | FastMCP HTTP | MCP tools + REST in one server |
| AI Classification | Gemini 2.5 Flash free tier | No GPU, no self-hosted model |
| CRM | HubSpot Free | Zero-cost CRM with real API |
| Notifications | Discord webhook | Zero-cost, instant |
| State | JSON flat-file | No database required |
| Scheduler | systemd timer | No cron, no cloud scheduler |

## How to Run

```bash
git clone https://github.com/AsmaIqbal01/openclaw-deal-scout
cd openclaw-deal-scout
pip install -e .
cp .env.example .env
python3.12 -m pytest -q
python3.12 -m openclaw_gateway
```

Dashboard: http://127.0.0.1:18790

## Architecture Decisions

Full ADR trail in history/adr/ — 8 documented decisions covering runtime
choice, state store, CRM write strategy, gateway transport, scheduler
architecture, and OAuth approach.

## What This Validated

- AI classification of inbound emails is viable on free-tier Gemini
- HubSpot Free CRM is sufficient for SMB lead management
- Discord webhook is a reliable zero-cost notification channel
- JSON flat-file state store handles real production load

## What is Next

Graduating to a vertical-specific product for real estate agents where
a missed lead means a lost commission.

Active development: https://github.com/AsmaIqbal01/-openclaw-deal-scout-realestate

## Built By

Asma Iqbal — AI Systems Architect
GitHub: https://github.com/AsmaIqbal01
