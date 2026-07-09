---
id: "003"
title: Git Checkpoint Skill Creation
stage: general
date: 2026-07-09
surface: agent
model: claude-sonnet-4-6
feature: none
branch: master
user: AsmaIqbal000
command: inline prompt
labels: ["skill","git","checkpoint","secret-scan","ci","tooling"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - .claude/skills/git-checkpoint/SKILL.md
tests:
  - null
---

## Prompt

Create a new Claude Code skill file at `.claude/skills/git-checkpoint/SKILL.md`
(create the folder if it doesn't exist).

CONTEXT:
This is for the "OpenClaw Deal Scout" project. Work happens in milestones
(subagent created, spec locked at 9.5+, plan/tasks generated, implementation
done, etc.). After each milestone, I want to commit and push to GitHub
(private repo, remote "origin", branch "main") — but ONLY after confirming
no secrets are about to be committed.

PURPOSE OF THIS SKILL:
A checklist/procedure Claude Code follows whenever asked to "checkpoint" or
"commit this milestone" to git. It must:
1. Run `git status` and `git diff --cached` to review staged/unstaged changes
2. Scan all changed files for secret patterns before staging anything
3. Present a staged-file manifest and pause for human approval
4. Stage only the approved, non-secret files explicitly (never git add .)
5. Commit with a milestone-scoped message
6. Push to origin/main (non-force)
7. Report result with commit SHA and next milestone hint

## Response snapshot

Created `.claude/skills/git-checkpoint/SKILL.md` with 6 sequential steps:

Step 1: Capture current state (git status, git diff --stat, git diff --cached --stat)
Step 2: Secret scan — 10 regex patterns covering OpenAI/GitHub/Google/Bearer/Discord/
        HubSpot/OAuth tokens, plus filename-based flags (.env, token.json, etc.)
        Outputs CLEAN or BLOCKED; BLOCKED halts the entire procedure.
Step 3: Build staged-file manifest — per-file ✅/⛔ status with brief descriptions
Step 4: Human approval gate — always pauses, requires explicit "yes"-equivalent reply
Step 5: Stage (explicit file list only), commit (heredoc message with milestone label
        + Co-Authored-By), push to origin/main; handles non-fast-forward rejection
Step 6: Success report with short SHA, file count, milestone label, next-step hint

Six hard invariants at the bottom: no .env, no git add ., no force-push, no skip
of approval gate, no amend of pushed commits, no commit when BLOCKED.

## Outcome

- ✅ Impact: Project now has a reusable, secret-safe git workflow for every
  milestone boundary — Claude Code follows the 6-step procedure whenever
  "checkpoint" or "commit this milestone" is used.
- 🧪 Tests: N/A (skill definition; tested by invocation at next milestone)
- 📁 Files: .claude/skills/git-checkpoint/SKILL.md
- 🔁 Next prompts: use /git-checkpoint after first spec is locked at 9.5+
- 🧠 Reflection: Secret scan covers project-specific credential types (HubSpot
  Service Key, Discord webhook URLs, Gmail OAuth tokens) plus generic patterns,
  so it's calibrated to the actual risk surface of this project.

## Evaluation notes (flywheel)

- Failure modes observed: none at authoring time
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): initial authoring
- Next experiment: test BLOCKED path by intentionally including a .env file
  in a dry-run to verify the halt behavior works correctly
