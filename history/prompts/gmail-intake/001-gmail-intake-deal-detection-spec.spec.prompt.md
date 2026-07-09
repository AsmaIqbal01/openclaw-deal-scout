---
id: "001"
title: Gmail Intake Deal Detection Spec
stage: spec
date: 2026-07-09
surface: agent
model: claude-sonnet-4-6
feature: gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: /sp.specify
labels: ["spec","gmail","deal-detection","fastmcp","idempotency","dealpayload"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/001-gmail-intake/spec.md
  - specs/001-gmail-intake/checklists/requirements.md
tests:
  - null
---

## Prompt

gmail intake pipeline step Build the Gmail Intake & Deal Detection module for
OpenClaw Deal Scout — a FastMCP tool that OpenClaw's Gemini-powered agent calls
to check for new business deal emails and extract structured deal data.

SCOPE (strictly limited to this step — do not include HubSpot, Discord, or
orchestration logic):
- Gmail is the only intake source (no scraping, no RSS, no webhooks)
- This step ends by producing a validated DealPayload — it does not create
  CRM records or send notifications; those are separate steps downstream

FUNCTIONAL REQUIREMENTS:
1. Gmail polling
   - Expose a FastMCP tool `check_new_deals` that OpenClaw's agent can call
   - Uses the existing Gmail OAuth credentials (Production consent screen,
     already configured) to poll the inbox for new/unread messages since
     the last successful check
   - Must work headlessly — no runtime browser-login step, ever (per
     Constitution Principle III)

2. Deal detection
   - For each new email, use Gemini (2.5 Flash, free tier) to classify:
     is this email describing a genuine business deal opportunity (e.g. a
     lead, an inquiry, a partnership offer) targeted at UK micro-businesses
     (sub-10-employee segment), or is it not a deal?
   - Define the exact prompt/schema used for this classification
   - Emails classified as "not a deal" are logged and skipped

3. Structured extraction (DealPayload contract)
   - gmail_message_id, sender_email, sender_name, subject, received_at,
     deal_summary, deal_category, confidence_score, raw_email_excerpt
   - Define exact types, required/optional, validation rules per field
   - Specify schema validation failure behavior

4. Idempotency / state store (Constitution Principle IV)
   - Record every gmail_message_id before returning success
   - Define crash recovery / partial state behavior

5. Error handling (Constitution Principle VI)
   - Gmail auth/token expiry, Gmail rate limit, Gemini 429, malformed body,
     empty inbox, network failure mid-poll

EDGE CASES: duplicate message ID, empty body, non-English email, long body
(8,000 char cap), multiple deals in one thread

OUT OF SCOPE: HubSpot, Discord, orchestration, multi-account Gmail

SUCCESS CRITERIA: N-email test inbox — correct classification, zero duplicates,
zero crashes, idempotent second run.

## Response snapshot

Spec written to `specs/001-gmail-intake/spec.md` on branch `001-gmail-intake`.

3 user stories:
- P1: Unattended Deal Detection (3 acceptance scenarios)
- P2: Structured Deal Data Extraction (3 acceptance scenarios)
- P3: Idempotent Re-runs (2 acceptance scenarios)

7 edge cases explicitly covered.

20 functional requirements (FR-001–FR-020) across 5 areas: polling, classification,
extraction, idempotency, error handling.

3 key entities with typed contracts: DealPayload (9 fields with types/validation),
ProcessedMessage (3 fields with outcome enum), ClassificationRequest (5 input fields).

5 measurable, technology-agnostic success criteria (SC-001–SC-005).

Explicit Out of Scope section. Quality checklist at checklists/requirements.md —
all items pass.

## Outcome

- ✅ Impact: Feature spec for Gmail Intake step complete; no [NEEDS CLARIFICATION]
  markers; DealPayload contract fully typed; all 6 error conditions specified with
  per-condition behavior.
- 🧪 Tests: N/A (spec document)
- 📁 Files: specs/001-gmail-intake/spec.md, specs/001-gmail-intake/checklists/requirements.md
- 🔁 Next prompts: run spec-scorer subagent against this spec; if PASS run /sp.plan
- 🧠 Reflection: Tension between "technology-agnostic spec" and "concretely typed
  interface" resolved by putting typed contracts in Key Entities (data modeling)
  rather than in FRs (behavioral requirements). The classifier prompt details are
  deferred to plan deliberately — spec defines WHAT is required, plan defines HOW.

## Evaluation notes (flywheel)

- Failure modes observed: none — user prompt was extremely detailed and left no
  ambiguity; zero [NEEDS CLARIFICATION] markers needed
- Graders run and results (PASS/FAIL): checklist self-validation PASS (all items)
- Prompt variant (if applicable): first spec for this feature
- Next experiment: run spec-scorer subagent to get objective rubric score before
  committing to /sp.plan
