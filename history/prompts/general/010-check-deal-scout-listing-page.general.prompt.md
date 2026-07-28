---
id: 010
title: Check deal-scout ClawHub listing page
stage: general
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: none
branch: main
user: AsmaIqbal01
command: none
labels: ["clawhub", "verification"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files: []
tests:
 - WebFetch https://clawhub.ai/skills/deal-scout (SPA shell only, no rendered data)
 - WebFetch https://clawhub.ai/api/v1/skills/deal-scout (authoritative JSON data)
---

## Prompt

check the deal-scout listing page

## Response snapshot

Fetched `https://clawhub.ai/skills/deal-scout` first; it returned only the client-side-rendered SPA shell (nav links, generic marketing copy, "30 skills / 12 plugins" counts) with no actual listing data — consistent with the earlier ClawHub research finding that the site is JS-heavy and doesn't render through a static HTML fetch. Fetched the underlying `https://clawhub.ai/api/v1/skills/deal-scout` endpoint directly instead, which returned the real record: slug `deal-scout`, owner `@asmaiqbal01` (Asma Iqbal, userId `s178xb05s2zqn8bf5nf1z00a4s8bdhh7`), version `1.0.0`, license `MIT-0`, description matching the SKILL.md summary verbatim, homepage pointing at the GitHub repo, and stats at 0 downloads/installs/stars/comments (expected for a freshly published skill). This endpoint didn't surface moderation data, but that was already confirmed clean (`verdict: "clean"`, `scanner.llm.clean`) via `clawhub inspect` in the prior publish-verification session. Reported to the user that visually inspecting stars/badges on the rendered page requires an actual browser, since WebFetch cannot execute the SPA's client-side JS.

## Outcome

- ✅ Impact: Confirmed the public listing data is correct and matches the published SKILL.md content — no drift between what was published and what ClawHub is serving.
- 🧪 Tests: API fetch — PASS (all fields match expected values); SPA page fetch — inconclusive by design (client-rendered, not a failure).
- 📁 Files: none (verification only)
- 🔁 Next prompts: none pending.
- 🧠 Reflection: For JS-rendered sites, prefer the site's own JSON API endpoints over WebFetch-ing the HTML page when verifying data — faster and authoritative, without guessing at what the client-side render would show.

## Evaluation notes (flywheel)

- Failure modes observed: WebFetch against a client-rendered SPA page returns only the shell — not a bug, just a tool/site mismatch to route around via the API instead.
- Graders run and results (PASS/FAIL): API data cross-check against SKILL.md — PASS.
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
