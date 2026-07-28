---
id: 019
title: Tighten deal classifier rejection rules
stage: green
date: 2026-07-29
surface: agent
model: claude-sonnet-5
feature: 001-gmail-intake
branch: main
user: AsmaIqbal01
command: none
labels: ["classifier", "gemini-prompt", "confidence-threshold", "tests"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - src/gmail_intake/classifier.py
 - src/gmail_intake/server.py
 - tests/unit/test_classifier.py
tests:
 - tests/unit/test_classifier.py (7 tests, all passing)
---

## Prompt

claude "In ~/openclaw-deal-scout, find the Gemini classification prompt — check src/gmail_intake.py first, then grep for 'deal_category' if not there.Make EXACTLY these changes, nothing else:CHANGE 1 — In the Gemini prompt string, insert this block immediately after the deal_category enum definition:---STRICT REJECTION RULES (check before scoring confidence):Classify is_deal=false immediately if ANY of these match:- Sender address contains: noreply@, newsletters-noreply@, digest@, no-reply@
- Email body contains the word 'unsubscribe'
- Email is a broadcast/digest (LinkedIn Newsletter, Substack, etc.)
- No personalized mention of the recipient's business by name or specific context
If any rule matches, set is_deal=false and confidence_score=0.0, skip remaining analysis.
---

CHANGE 2 — Find the confidence threshold check (currently likely 0.7 or 0.5) and change it to:
if confidence_score < 0.85: log as skipped, do not pass to HubSpot or Discord

CHANGE 3 — In tests/test_gmail_intake.py, add one new test:
test_newsletter_rejected: feed a mock email with sender 'newsletters-noreply@linkedin.com' and body containing 'unsubscribe', assert is_deal=False and confidence_score=0.0

Show unified diff of all three changes BEFORE applying anything.
Type STOP and wait for me to respond 'yes' before making any edits."

---

yes

---

claude "In ~/openclaw-deal-scout, find the Gemini classification prompt — check src/gmail_intake.py first, then grep for 'deal_category' if not there.Make EXACTLY these changes, nothing else:CHANGE 1 — In the Gemini prompt string, insert this block immediately after the deal_category enum definition:---STRICT REJECTION RULES (check before scoring confidence):Classify is_deal=false immediately if ANY of these match:- Sender address contains: noreply@, newsletters-noreply@, digest@, no-reply@- Email body contains the word 'unsubscribe'
- Email is a broadcast/digest (LinkedIn Newsletter, Substack, etc.)
- No personalized mention of the recipient's business by name or specific context
If any rule matches, set is_deal=false and confidence_score=0.0, skip remaining analysis.

EXAMPLE MESSAGES — use these as ground truth for classification:

❌ NOT A DEAL (is_deal=false, confidence=0.0):
Subject: 'GenAI Works is offering micro-businesses AI tools to feature their products'
From: newsletters-noreply@linkedin.com
Reason: mass LinkedIn newsletter, unsubscribe link present, no direct recipient mention

❌ NOT A DEAL (is_deal=false, confidence=0.0):
Subject: 'Anthropic deleted 80% of its Claude Code prompt'
From: digest@spideybot.discord
Reason: automated digest/notification, not a business opportunity directed at recipient

✅ IS A DEAL (is_deal=true, confidence>=0.85):
Subject: 'Partnership inquiry for your AI automation services'
From: john.smith@acmeltd.co.uk
Body: 'Hi, I found your profile and I'm looking for someone to automate our invoicing workflow. Can we get on a call this week?'
Reason: direct, personalized, names a specific need, sent to this recipient specifically
---

CHANGE 2 — Find the confidence threshold check and change it to:
if confidence_score < 0.85: log as skipped, do not pass to HubSpot or Discord

CHANGE 3 — In tests/test_gmail_intake.py, add two new tests:
- test_newsletter_rejected: mock email from 'newsletters-noreply@linkedin.com' with 'unsubscribe' in body → assert is_deal=False, confidence_score=0.0
- test_discord_digest_rejected: mock email from 'digest@spideybot.discord' with no business context → assert is_deal=False, confidence_score=0.0
- test_direct_inquiry_passes: mock email from 'john.smith@acmeltd.co.uk' with personalized partnership ask → assert is_deal=True, confidence_score>=0.85

Show unified diff of all three changes BEFORE applying anything.
Type STOP and wait for me to respond 'yes' before making any edits."

---

yes

## Response snapshot

Located the Gemini prompt in `src/gmail_intake/classifier.py` (not `src/gmail_intake.py`, which doesn't exist) via grep for `deal_category`. Flagged two path discrepancies from the user's request: (1) the confidence-threshold gate that actually skips HubSpot/Discord delivery lives in `src/gmail_intake/server.py:181`, not in classifier.py; (2) `tests/test_gmail_intake.py` doesn't exist — used `tests/unit/test_classifier.py` instead, and noted that its tests mock `genai.Client` entirely, so new tests verify JSON-parsing behavior against a canned mock response, not that Gemini actually applies the new prompt rules.

Applied in two rounds (each preceded by a unified diff and an explicit STOP for user confirmation):
1. Inserted a STRICT REJECTION RULES block into the `_PROMPT_TEMPLATE` string in classifier.py, immediately after the `deal_category` enum rule (item 7).
2. Changed the confidence gate in server.py from `< 0.5` to `< 0.85`.
3. Added `test_newsletter_rejected` to test_classifier.py.
4. On the follow-up request: extended the STRICT REJECTION RULES block with an EXAMPLE MESSAGES section (3 worked examples); added `test_discord_digest_rejected` and `test_direct_inquiry_passes`.

Fixed one self-introduced bug during the second round: an over-escaped apostrophe (`\\'`) inside a Python single-quoted string broke the file with `SyntaxError: unterminated string literal`; corrected by removing the unnecessary escape (JSON only requires escaping double quotes).

## Outcome

- ✅ Impact: Gemini classification prompt now hard-rejects noreply/digest/newsletter senders and unsubscribe-bearing bodies before scoring, with 3 worked examples embedded in-prompt; downstream HubSpot/Discord delivery now gated at confidence_score >= 0.85 instead of >= 0.5.
- 🧪 Tests: `tests/unit/test_classifier.py` — 7/7 passing (4 pre-existing + `test_newsletter_rejected`, `test_discord_digest_rejected`, `test_direct_inquiry_passes`).
- 📁 Files: src/gmail_intake/classifier.py, src/gmail_intake/server.py, tests/unit/test_classifier.py
- 🔁 Next prompts: Consider an integration/live-smoke test against the real Gemini API to confirm the model actually honors the new prompt rules, since unit tests only exercise the mocked JSON-parsing path.
- 🧠 Reflection: User-supplied file paths (`src/gmail_intake.py`, `tests/test_gmail_intake.py`) didn't match the actual repo layout — always verify paths exist before diffing/editing rather than assuming the user's paths are current.

## Evaluation notes (flywheel)

- Failure modes observed: Self-introduced Python syntax error from unnecessary backslash-escaping an apostrophe inside a single-quoted JSON string literal; caught immediately by running the test suite.
- Graders run and results (PASS/FAIL): pytest tests/unit/test_classifier.py — PASS (7/7)
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): Add a live/integration test hitting real Gemini API with one of the EXAMPLE MESSAGES to confirm actual model compliance with the new STRICT REJECTION RULES, closing the gap the mocked unit tests can't cover.
