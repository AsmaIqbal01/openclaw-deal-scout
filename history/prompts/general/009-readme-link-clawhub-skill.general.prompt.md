---
id: 009
title: Link ClawHub skill from README
stage: general
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: none
branch: main
user: AsmaIqbal01
command: none
labels: ["docs", "readme", "clawhub"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - README.md
tests: []
---

## Prompt

update the README to link the ClawHub skill

## Response snapshot

Added a short link to the published ClawHub skill (https://clawhub.ai/skills/deal-scout, slug `deal-scout`) at the top of the "How to run locally" section in `README.md`, framed as an alternative discovery path for operators driving setup from an OpenClaw agent rather than a plain shell. Kept the change to a single addition — no other README sections touched.

## Outcome

- ✅ Impact: README now points readers to the live, publicly-searchable ClawHub listing alongside the manual clone/setup instructions.
- 🧪 Tests: n/a (docs-only change)
- 📁 Files: README.md
- 🔁 Next prompts: none pending.
- 🧠 Reflection: n/a

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): n/a
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
