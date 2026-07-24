---
id: "0001"
title: Workspace Backup to GitHub
stage: general
date: 2026-07-24
surface: agent
model: claude-sonnet-4-6
feature: none
branch: main
user: AsmaIqbal01
command: back up ~/.openclaw/workspace/ to a private GitHub repo
labels: ["general","backup","github","workspace","devops"]
links:
  spec: "null"
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - ~/.openclaw/workspace/.gitignore        # created: excludes .openclaw/, secrets, caches
  - ~/.openclaw/workspace/SOUL.md           # backed up
  - ~/.openclaw/workspace/IDENTITY.md       # backed up
  - ~/.openclaw/workspace/AGENTS.md         # backed up
  - ~/.openclaw/workspace/TOOLS.md          # backed up
  - ~/.openclaw/workspace/HEARTBEAT.md      # backed up
  - ~/.openclaw/workspace/BOOTSTRAP.md      # backed up
  - ~/.openclaw/workspace/USER.md           # backed up
tests: []
---

## Prompt

Back up ~/.openclaw/workspace/ to a private GitHub repo. Include all workspace files, exclude secrets and caches. Give me a recovery one-liner when done.

## Response snapshot

Created private GitHub repo `AsmaIqbal01/openclaw-workspace` and pushed 8 files from `~/.openclaw/workspace/`:

- `.gitignore` — excludes `.openclaw/` runtime state, `*.sqlite*`, `*.jsonl`, `memory/*.json`, `.env`, `token.json`, `credentials.json`
- `SOUL.md`, `IDENTITY.md`, `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`, `USER.md`

The `.openclaw/workspace-state.json` (runtime state, just a bootstrap timestamp) was excluded via `.gitignore`.

Repo URL: https://github.com/AsmaIqbal01/openclaw-workspace
Initial commit: 8 files, 500 insertions on branch `main`.

Recovery one-liner:
```bash
git clone https://github.com/AsmaIqbal01/openclaw-workspace.git ~/.openclaw/workspace
```

## Outcome

- ✅ Impact: Workspace identity files durably backed up to private GitHub repo
- 📁 Files: 8 committed; secrets and runtime state excluded
- 🔁 Future: run `cd ~/.openclaw/workspace && git add -u && git commit -m "..." && git push` after updating any workspace file
