---
id: "028"
title: Live E2E Pipeline Smoke Test
stage: green
date: 2026-07-18
surface: agent
model: claude-sonnet-4-6
feature: 003-discord-notification
branch: 002-hubspot-crm-logger
user: AsmaIqbal000
command: live end-to-end pipeline test
labels: ["live-test","hubspot","discord","e2e","smoke-test","crm-properties"]
links:
  spec: specs/003-discord-notification/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - C:\Users\umzaid\AppData\Roaming\Claude\claude_desktop_config.json
  - scratchpad/inject_and_run.py
  - scratchpad/create_hubspot_properties.py
tests:
  - Live inject-and-run: deal_extracted -> crm-logged -> discord-notified (4 entries)
---

## Prompt

updated and rotated token [after adding crm.schemas.deals.write scope to HubSpot private app]

(Prior context: live end-to-end pipeline test blocked on HubSpot 403 missing scopes, then 400 PROPERTY_DOESNT_EXIST for all 5 openclaw custom deal properties. Token had been rotated twice previously for scope additions.)

## Response snapshot

1. Read new token from .env (`pat-na2-***REDACTED***`), updated `claude_desktop_config.json`.
2. Created all 5 custom HubSpot deal properties via API (`crm.schemas.deals.write` scope):
   - `openclaw_deal_category` (text)
   - `openclaw_confidence_score` (text)
   - `openclaw_deal_summary` (textarea)
   - `openclaw_received_date` (text)
   - `openclaw_gmail_message_id` (text)
3. Ran `inject_and_run.py` — injected synthetic `deal_extracted` entry, executed Steps 2 and 3.
4. Result: `crm_logged: 4, notify_pending: 0` / `discord_notified: 4, notify_pending: 0`. Final entry status: `discord-notified` with `hubspot_deal_id: 336630426353` and `notified_at` written.

## Outcome

- ✅ Impact: Full Steps 2+3 pipeline proven live — HubSpot deal created (ID 336630426353), Discord notified, state store written to `discord-notified`. 3 previously stuck `crm-pending` entries also drained successfully.
- 🧪 Tests: Live smoke test with synthetic `deal_extracted` entry injected directly into state store
- 📁 Files: `claude_desktop_config.json` (token updated); scratchpad scripts created and executed
- 🔁 Next prompts: T025 (noop smoke test manual), real Gmail email trigger for Step 1 end-to-end
- 🧠 Reflection: Root causes resolved in sequence: 403 (missing CRM write scopes) → 400 PROPERTY_DOESNT_EXIST (custom properties not in correct HubSpot portal 246716769) → resolved by adding `crm.schemas.deals.write` and creating properties via API

## Evaluation notes (flywheel)

- Failure modes observed: HubSpot portal mismatch (user creating properties in wrong portal via UI); token rotation required 3 times for scope additions; Gmail send not viable with readonly OAuth scope
- Graders run and results (PASS/FAIL): Live pipeline PASS — crm_logged:4, discord_notified:4
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Test Step 1 (Gmail intake) with a real inbound email from external sender to trigger full 3-step pipeline
