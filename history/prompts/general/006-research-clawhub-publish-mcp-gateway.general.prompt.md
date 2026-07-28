---
id: 006
title: Research ClawHub and publish MCP gateway
stage: general
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: none
branch: main
user: AsmaIqbal01
command: none
labels: ["docs", "clawhub", "mcp", "publishing", "research"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - clawhub/openclaw-deal-scout/SKILL.md
tests:
 - clawhub skill publish ./clawhub/openclaw-deal-scout --dry-run --json (validation only, no test files changed)
---

## Prompt

Now research ClawHub and publish our MCP gateway to it

## Response snapshot

Researched ClawHub before touching anything, since publishing is a public, hard-to-reverse action requiring the user's own login. Found: ClawHub is the public skill/plugin registry for "OpenClaw," an unrelated open-source AI-agent-skill ecosystem (github.com/openclaw/openclaw) — a pure naming coincidence with this project's own "OpenClaw Deal Scout" name, not shared ownership. Publishing works via an npm-distributed `clawhub` CLI (`clawhub login`, `clawhub skill publish <path>` or `clawhub package publish <source>`), requires a GitHub-linked account, and skills publish under MIT-0.

Surfaced two decision points to the user rather than assuming: (1) whether to actually make the gateway public given the README states the project is proprietary — user chose yes; (2) how to reconcile ClawHub's MCP-plugin model (a concrete example, `@dataify-server/dataify-mcp`, showed plugins point at a publicly-hosted remote MCP endpoint, not local code) with this project's explicitly local-only, zero-infrastructure architecture (ADR-0002/0004/0005) — user chose to publish as a GitHub-linked "skill" (setup/usage docs pointing at the existing public repo) rather than standing up new public hosting.

Built `clawhub/openclaw-deal-scout/SKILL.md` with full frontmatter (required env vars, primary env, emoji, homepage) and a body covering setup steps, the four MCP tools (`run_cycle`, `get_pipeline_cycles`, `get_deals`, `get_quota_usage`), and explicit constraints for any agent using the skill (don't suggest paid tiers, don't propose migrating the JSON state store, don't bypass the UK business-hours send gate). Installed the `clawhub` CLI locally (`npm i -g clawhub`) to dry-run validate the manifest before any real upload: first attempt slugged as `clawhub-skill` because ClawHub derives the publish slug from the *folder name*, not the `name:` frontmatter field — caught this before it could publish under the wrong slug and renamed the folder to `openclaw-deal-scout`. Re-ran the dry-run: `slug: openclaw-deal-scout, version: 1.0.0, fileCount: 1` — confirming only the manifest gets bundled, not the proprietary source tree (verified the GitHub repo's own visibility is `PUBLIC` via `gh repo view`, so the setup instructions' `git clone` link is actually reachable).

Did not run the actual `clawhub login` / `clawhub skill publish` (no dry-run) step — that requires the user's own GitHub-linked credentials for a public, one-way action, which the agent cannot and should not perform on the user's behalf. Committed and pushed the manifest file only (commit `d2161aa`) after explicit user confirmation.

## Outcome

- ✅ Impact: Project is publish-ready on ClawHub as a documentation-only skill; the user retains the actual publish action (identity-bound, one-way) rather than the agent taking an irreversible external action with implied consent.
- 🧪 Tests: `clawhub skill publish ./clawhub/openclaw-deal-scout --dry-run --json` — PASS (`ok: true`, `fileCount: 1`, no proprietary files bundled).
- 📁 Files: clawhub/openclaw-deal-scout/SKILL.md (created)
- 🔁 Next prompts: user runs `clawhub login` then `clawhub skill publish ./clawhub/openclaw-deal-scout` themselves when ready.
- 🧠 Reflection: A vague instruction ("publish our MCP gateway to it") concealed two real forks — public-vs-proprietary licensing, and local-only architecture vs. ClawHub's hosted-endpoint MCP model — that a naive execution would have gotten wrong (either open-sourcing the whole repo under MIT-0, or standing up unwanted public infrastructure). Surfacing them as explicit choices before writing anything caught both.

## Evaluation notes (flywheel)

- Failure modes observed: ClawHub's publish slug is derived from folder name, not the manifest's `name:` field — an easy silent-mismatch trap; caught only by dry-running before any real publish.
- Graders run and results (PASS/FAIL): dry-run validation — PASS; repo-visibility check (`gh repo view`) — PASS (confirmed PUBLIC before linking to it from a public skill).
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
