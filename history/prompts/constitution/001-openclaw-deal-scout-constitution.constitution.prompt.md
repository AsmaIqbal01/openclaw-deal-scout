---
id: "001"
title: OpenClaw Deal Scout Constitution
stage: constitution
date: 2026-07-08
surface: agent
model: claude-sonnet-4-6
feature: none
branch: master
user: AsmaIqbal000
command: /sp.constitution
labels: ["constitution","zero-cost","gmail","hubspot","discord","headless","deal-scout"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - .specify/memory/constitution.md
  - history/prompts/constitution/001-openclaw-deal-scout-constitution.constitution.prompt.md
tests:
  - null
---

## Prompt

Build the constitution for "OpenClaw Deal Scout" — a Digital FTE product for
Pakistani SMBs and freelancers that automates deal capture, CRM logging, and
notification, 24/7, at zero infrastructure cost.

Non-negotiable principles:
1. Zero cost — no paid APIs, no paid hosting, no paid notification channels.
2. Single intake source for MVP — Gmail only. No scraping, RSS, or webhook
   intake in this version.
3. Headless/unattended operation — no step in the pipeline may require a
   human to complete a browser login at runtime.

Architecture (already built and running — describe accurately, don't invent
alternatives):
- Orchestrator: OpenClaw (Node.js-based agent gateway, self-hosted via
  systemd on the operator's machine)
- Input: Gmail API (OAuth, testing mode)
- LLM: Google Gemini 2.5 Flash (free tier, configured as OpenClaw's default model)
- CRM: HubSpot Free CRM, accessed via a private-app-token MCP server
  (not the official OAuth-only HubSpot MCP, since that requires browser login)
- Output: Discord (native OpenClaw channel, connected to #deal_alerts)

Include:
- State management: track already-notified/already-logged deals (e.g. by
  Gmail message ID) to prevent duplicate CRM entries and duplicate alerts
- Modularity: the notification target must be swappable (Discord → Slack/
  Email/SMS) via a single config block, without touching core deal-detection
  or CRM logic
- Error handling: defined fallback behavior for (a) Gemini API rate limits,
  (b) Discord webhook/API failures, (c) HubSpot rate limits (100 req/10 sec
  on free tier), (d) Gmail token expiry — each should log and retry/skip
  gracefully, never crash the agent

## Response snapshot

Constitution v1.0.0 written to `.specify/memory/constitution.md` with 6 principles:

I.   Zero Cost Infrastructure (NON-NEGOTIABLE) — prohibits any paid dependency
II.  Gmail-Only Intake (MVP NON-NEGOTIABLE) — single intake source discipline
III. Headless / Unattended Operation (NON-NEGOTIABLE) — no runtime browser logins
IV.  State-Driven Idempotency — Gmail message ID state store prevents duplicates
V.   Modular Notification Architecture — notifier adapter pattern, config-driven swap
VI.  Graceful Degradation & Error Resilience — per-failure-mode fallback table

Technology Stack & Architecture section documents the live running stack accurately.
Constitution Check Gates defined (6 gates) for use in plan.md and code review.
Development Workflow & Quality Gates section covers secrets, logging levels, and PHR
requirement. Governance section defines amendment procedure, versioning policy, and
compliance review expectations.

## Outcome

- ✅ Impact: Project constitution established from scratch; all 6 principles are
  declarative, testable, and free of vague language. All placeholder tokens replaced.
- 🧪 Tests: N/A (constitution document; no automated tests applicable)
- 📁 Files: .specify/memory/constitution.md (created/overwritten), history/prompts/constitution/001-openclaw-deal-scout-constitution.constitution.prompt.md (created)
- 🔁 Next prompts: /sp.specify <feature-name> to write the first feature spec against this constitution; /sp.adr if architectural decisions surface during planning
- 🧠 Reflection: User provided all 3 non-negotiable principles and the full live
  architecture stack explicitly — no inference needed. The 3 additional principles
  (IV, V, VI) were derived directly from the "Include:" section of the prompt.

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): manual validation — all placeholders resolved, dates ISO, version 1.0.0
- Prompt variant (if applicable): initial authoring
- Next experiment: test whether Constitution Check Gates in plan-template.md need explicit wording updates referencing these 6 principles
