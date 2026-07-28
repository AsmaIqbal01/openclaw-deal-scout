---
id: 007
title: Publish deal-scout skill to ClawHub
stage: general
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: none
branch: main
user: AsmaIqbal01
command: none
labels: ["clawhub", "publishing", "mcp", "ops"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - clawhub/deal-scout/SKILL.md (renamed from clawhub/openclaw-deal-scout/SKILL.md)
tests:
 - clawhub skill publish /home/asmaiqbal01/openclaw-deal-scout/clawhub/deal-scout --dry-run --json (validation)
 - clawhub skill publish /home/asmaiqbal01/openclaw-deal-scout/clawhub/deal-scout --json (real publish)
 - clawhub inspect deal-scout --json (post-publish moderation check: verdict "clean")
---

## Prompt

publish it

[mid-turn, after device-login code was issued and while still polling]: done, publish it now

[mid-turn system-relayed message]: I already logged in successfully in another terminal as @AsmaIqbal01. The SKILL.md exists but publish fails with "SKILL.md required". Run clawhub skill validate from inside the clawhub/openclaw-deal-scout directory and fix the format issue.

[clarifying-question answer]: deal-scout (chosen as the replacement slug after "openclaw-deal-scout" was rejected)

yes create a PHR for this

## Response snapshot

Started the device-flow login (`clawhub login --device`) since the CLI wasn't authenticated yet, surfaced the code/URL to the user, and waited. When the user reported logging in via a separate terminal, `clawhub whoami` still showed "Not logged in" from this agent's shell — root-caused to an environment mismatch: prior commands ran through a Windows-side Git Bash shell (`HOME=/c/Users/umzaid`, token store at `AppData/Roaming/clawhub`), while the user's actual project and login lived in the native WSL Ubuntu-22.04 distro (`HOME=/home/asmaiqbal01`) — same `clawhub` binary (installed once via npm, reachable through the `/mnt/c` passthrough), but two separate config/token stores depending on which side invoked it. Switched to running clawhub commands via `wsl.exe -d Ubuntu-22.04 -- bash -lc "..."` to operate in the environment where the user was actually authenticated; confirmed with `whoami` → `AsmaIqbal01`.

The user's suggested `clawhub skill validate` subcommand doesn't exist in this CLI version (v0.23.1) — `clawhub skill --help` lists only `publish|verify|rename|merge`. Reproduced the "SKILL.md required"-shaped failure via `--dry-run` and found the actual cause: a CLI bug where a **relative** path (`./clawhub/openclaw-deal-scout`) fails with `Path must be a folder`, while the equivalent **absolute** path resolves and validates correctly — not a SKILL.md format problem at all. Re-ran the real (non-dry-run) publish with the absolute path; it rejected the slug with `"openclaw-deal-scout" uses the protected "openclaw" slug namespace` (ClawHub reserves the `openclaw-` prefix for its own ecosystem, unrelated to this project's coincidental name). Asked the user for a replacement slug rather than picking one silently, since it's a permanent public identifier; user chose `deal-scout`. Renamed the folder (`git mv clawhub/openclaw-deal-scout clawhub/deal-scout` — slug is derived from folder name, confirmed earlier in the ClawHub research session, not from the `name:` frontmatter field), re-validated with `--dry-run` (same content fingerprint as before), then published for real: `status: "published"`, `slug: "deal-scout"`, `version: "1.0.0"`. Confirmed clean via `clawhub inspect deal-scout` (`moderation.verdict: "clean"`, no suspicious patterns flagged). Committed and pushed the folder rename (`ddcf211`).

## Outcome

- ✅ Impact: `deal-scout` v1.0.0 is live and published on ClawHub, security-scan clean; the earlier `openclaw-deal-scout` naming never went public (caught pre-publish).
- 🧪 Tests: dry-run validation PASS; real publish PASS (`status: "published"`); post-publish moderation check PASS (`verdict: "clean"`).
- 📁 Files: clawhub/deal-scout/SKILL.md (renamed folder, content unchanged from prior commit)
- 🔁 Next prompts: none pending — publish is complete and live.
- 🧠 Reflection: Two silent environment-mismatch traps in one session — (1) Windows Git Bash vs. native WSL having separate `$HOME`/config stores for the same npm-installed binary, and (2) the CLI's own relative-vs-absolute path bug masquerading as a SKILL.md format error. Neither was in the user's or the agent's mental model going in; both needed direct reproduction (`whoami`, `--dry-run`) rather than trusting the first error message at face value.

## Evaluation notes (flywheel)

- Failure modes observed: (1) Multi-shell environments with a shared filesystem but separate `$HOME` silently split auth/config state for the same tool. (2) `clawhub skill publish <relative-path>` fails with a misleading "Path must be a folder" / "SKILL.md required"-shaped error; absolute paths work. (3) ClawHub reserves the `openclaw-` slug prefix — a project literally named "OpenClaw ___" will collide with it.
- Graders run and results (PASS/FAIL): dry-run — PASS; real publish — PASS; post-publish moderation scan — PASS (clean).
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
