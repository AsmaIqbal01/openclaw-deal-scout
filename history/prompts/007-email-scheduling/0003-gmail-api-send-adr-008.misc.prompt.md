---
id: "0003"
title: Gmail API Send ADR 008
stage: misc
date: 2026-07-26
surface: agent
model: claude-sonnet-4-6
feature: 007-email-scheduling
branch: 007-email-scheduling
user: AsmaIqbal01
command: /sp.adr gmail-api-send-vs-smtp
labels: ["adr","gmail-api","smtp","email-send","oauth2","007-email-scheduling"]
links:
  spec: specs/007-email-scheduling/spec.md
  ticket: "null"
  adr: history/adr/0008-gmail-api-send-vs-raw-smtp-for-outbound-email.md
  pr: "null"
files:
  - history/adr/0008-gmail-api-send-vs-raw-smtp-for-outbound-email.md
tests:
  - "null"
---

## Prompt

/sp.adr gmail-api-send-vs-smtp

## Response snapshot

Checked 7 existing ADRs (0001–0007) — no existing ADR covers outbound email send mechanism.
Significance test PASS (all 3 criteria): cross-cutting impact on email_scheduler.auth +
scheduler dispatch path + operator setup; clear alternatives with distinct tradeoffs;
will be questioned if Gmail quota or auth changes.

Created ADR-0008: Gmail API Send vs Raw SMTP for Outbound Email.

Decision cluster: Gmail REST API `users().messages().send()` with scope `gmail.send`;
`email.mime` + `base64` for message construction; credential loading mirrors
`gmail_intake.gmail_client`; 001-gmail-intake unchanged.

Three alternatives documented:
- Alternative A (raw smtplib + XOAUTH2): rejected — no native token refresh, separate
  error taxonomy, broader `https://mail.google.com/` scope required
- Alternative B (transactional email service): rejected — violates Constitution Principle I (zero cost)
- Alternative C (shared auth module extraction): deferred — changes 001-gmail-intake,
  contradicts spec constraint

## Outcome

- ✅ Impact: ADR-0008 created; gmail-api-send decision permanently documented with full alternatives and tradeoffs
- 🧪 Tests: none (ADR stage)
- 📁 Files: 1 ADR created
- 🔁 Next prompts: /sp.adr email-dispatch-threading-model, /sp.tasks
- 🧠 Reflection: Decision 3 (001-gmail-intake unchanged) and Decision 1 (Gmail API vs SMTP) are tightly coupled — documenting them as a single cluster was correct; splitting would have created an over-granular pair

## Evaluation notes (flywheel)

- Failure modes observed: create-adr.sh requires --title flag (not positional arg) — first attempt failed
- Graders run and results (PASS/FAIL): significance test PASS (all 3 criteria met)
- Prompt variant (if applicable): "null"
- Next experiment: "null"
