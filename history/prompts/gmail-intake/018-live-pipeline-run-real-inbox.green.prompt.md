---
id: "018"
title: Live Pipeline Run Against Real Gmail Inbox
stage: green
date: 2026-07-15
surface: agent
model: claude-sonnet-4-6
feature: 001-gmail-intake
branch: 001-gmail-intake
user: AsmaIqbal000
command: check_new_deals_handler (direct invocation)
labels: ["live-test","gmail","gemini","pipeline","credentials","portalocker","windows-wsl"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/gmail_intake/classifier.py
  - .env
tests:
  - check_new_deals_handler live invocation against real Gmail inbox
---

## Prompt

Run the check_new_deals MCP tool manually and show me the output against a real/test Gmail inbox. (Session continuation — credentials setup, dependency fixes, and final pipeline run.)

## Response snapshot

Pipeline ran end-to-end against the real Gmail inbox. Result:

```json
{
  "status": "ok",
  "deals_extracted": [],
  "processed_count": 19,
  "skipped_count": 19,
  "error_details": null
}
```

19 unread emails from the last 24 hours were fetched and classified by Gemini 2.5 Flash. All 19 were identified as non-deals (newsletters, notifications, personal mail). State store updated; idempotency confirmed.

## Outcome

- ✅ Impact: First successful live end-to-end run of the check_new_deals pipeline against a real Gmail inbox with real Gemini classification.
- 🧪 Tests: Live invocation — 19 emails processed, 0 deals extracted, no errors.
- 📁 Files: Fixed classifier.py import (google-genai SDK); .env credentials path corrected; google-genai 2.11.0 installed.
- 🔁 Next prompts: Run again after a real deal email arrives; consider verbose/debug mode to log per-message classification.
- 🧠 Reflection: Three environment issues were encountered and resolved: (1) GMAIL_CREDENTIALS_PATH set to client ID string instead of file path; (2) google-genai package not installed (classifier used new SDK, only old SDK was present); (3) portalocker file locking fails on WSL filesystem accessed via Windows UNC paths — resolved by routing STATE_STORE_PATH to a native Windows directory.

## Evaluation notes (flywheel)

- Failure modes observed: portalocker LOCK_EX fails with EINVAL on WSL 9P filesystem via UNC path; GMAIL_CREDENTIALS_PATH misunderstood as client ID vs file path; google-genai vs google-generativeai SDK mismatch.
- Graders run and results (PASS/FAIL): live invocation PASS (status: ok, no error_details).
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): Add per-message classification logging to diagnose borderline confidence scores.
