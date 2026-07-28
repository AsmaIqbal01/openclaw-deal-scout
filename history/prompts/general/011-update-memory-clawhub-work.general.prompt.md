---
id: 011
title: Update memory index with ClawHub work
stage: general
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: none
branch: main
user: AsmaIqbal01
command: none
labels: ["memory", "clawhub"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - (external, not repo-tracked) C:\Users\umzaid\.claude\projects\--wsl-localhost-Ubuntu-22-04-home-asmaiqbal01-openclaw-deal-scout\memory\clawhub_publishing.md
 - (external, not repo-tracked) C:\Users\umzaid\.claude\projects\--wsl-localhost-Ubuntu-22-04-home-asmaiqbal01-openclaw-deal-scout\memory\MEMORY.md
tests: []
---

## Prompt

update the MEMORY.md index with this ClawHub work

## Response snapshot

Added a new reference-type memory file, `clawhub_publishing.md`, to the persistent auto-memory system (outside the git repo). It records: the published listing (slug `deal-scout`, owner `@asmaiqbal01`, v1.0.0, MIT-0, manifest at `clawhub/deal-scout/SKILL.md`), and the operational gotchas discovered across the publish/verify sessions — slug is derived from folder name not SKILL.md frontmatter, ClawHub reserves the `openclaw-` prefix, the CLI's relative-path bug (`Path must be a folder`), the WSL-vs-Windows-Git-Bash split auth/config store (same npm-installed binary, two separate token locations depending on which shell invokes it), `clawhub search` lacking a `--json` flag, and the moderation-lag between "published" and searchable. Also included the exact republish command for future updates. Linked it from `MEMORY.md`'s index with a one-line hook. Chose "reference" as the memory type since this is operational knowledge about an external system, not something derivable by reading the repo's own code or git history.

## Outcome

- ✅ Impact: Future sessions won't need to rediscover the ClawHub CLI's slug/path/auth quirks from scratch before republishing or updating the skill listing.
- 🧪 Tests: n/a (memory-system update, not a code or repo change)
- 📁 Files: clawhub_publishing.md (new), MEMORY.md (index entry added) — both in the persistent memory store, not the git repo
- 🔁 Next prompts: none pending.
- 🧠 Reflection: n/a

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): n/a
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
