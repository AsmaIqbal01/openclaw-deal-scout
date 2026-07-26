---
id: "0001"
title: Email Scheduling Spec 007
stage: spec
date: 2026-07-25
surface: agent
model: claude-sonnet-4-6
feature: 007-email-scheduling
branch: 007-email-scheduling
user: AsmaIqbal01
command: /sp.specify
labels: ["spec","email-scheduling","gmail-smtp","send-time","operator-approval"]
links:
  spec: specs/007-email-scheduling/spec.md
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - specs/007-email-scheduling/spec.md
  - specs/007-email-scheduling/checklists/requirements.md
tests:
  - "null"
---

## Prompt

Feature: Email scheduling and smart send-time optimization (007)

Context: OpenClaw Deal Scout pipeline is live (001-006 complete, 321 tests passing). Gateway runs at port 18790. Dashboard live at http://127.0.0.1:18790. Branch to create: 007-email-scheduling

Problem: Currently the pipeline only DETECTS deals from incoming Gmail — it has no ability to SEND emails. When a deal is detected, the operator must manually follow up. This creates a gap between detection and action.

Goal:
1. When a deal is detected, automatically schedule a follow-up email
2. Operator can review scheduled emails in dashboard before they send
3. Emails send at optimal times (business hours UK timezone)
4. Full audit trail — every scheduled/sent/cancelled email logged

Constraints:
- Zero-cost (Gmail SMTP via existing OAuth — no SendGrid, no Mailgun)
- Existing 321 tests must stay green
- No new external services
- Operator approval before any email sends (safety gate)

Out of scope:
- AI-generated email content (future feature)
- Multi-recipient campaigns
- Email templates UI

## Response snapshot

Created branch 007-email-scheduling and wrote spec with 4 user stories (P1–P4) and 15 functional requirements:

- US1 (P1): Auto-schedule email when deal reaches discord-notified status
- US2 (P2): Operator review & approval gate — no email sends without explicit approval
- US3 (P3): Smart send-time — dispatch only within Mon–Fri 09:00–17:00 Europe/London (DST-aware)
- US4 (P4): Full audit trail — every lifecycle event logged within 5 seconds

Key decisions documented in Assumptions:
- Gmail OAuth needs SMTP send scope added (one-time re-auth required)
- Email state stored in `email_queue.json` alongside `processed_ids.json`
- Send-time scheduler piggy-backs on existing 15-min pipeline cycle

All 16 checklist items PASS. No NEEDS CLARIFICATION markers.

## Outcome

- ✅ Impact: 007-email-scheduling spec ready; branch created; closes detection→action gap in pipeline
- 🧪 Tests: none yet (spec stage)
- 📁 Files: 2 files created (spec.md, checklists/requirements.md)
- 🔁 Next prompts: /sp.plan
- 🧠 Reflection: Gmail SMTP scope upgrade is a prerequisite that must surface early in planning — flagged in Assumptions and Dependencies

## Evaluation notes (flywheel)

- Failure modes observed: /sp.specify input was not reaching the tool for 3 attempts due to UI paste issue — workaround was plain-text message
- Graders run and results (PASS/FAIL): checklist 16/16 PASS
- Prompt variant (if applicable): "null"
- Next experiment: "null"
