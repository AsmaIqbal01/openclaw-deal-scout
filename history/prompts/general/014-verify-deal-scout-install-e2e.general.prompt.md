---
id: 014
title: Verify deal-scout skill install end-to-end
stage: general
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: none
branch: main
user: AsmaIqbal01
command: none
labels: ["clawhub", "verification", "install"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files: []
tests:
 - clawhub install deal-scout (isolated scratch directory)
 - diff installed SKILL.md against clawhub/deal-scout/SKILL.md source
 - clawhub list (post-install registration check)
---

## Prompt

check the deal-scout skill install works end-to-end

## Response snapshot

Ran `clawhub install --help` to confirm the install target is a local `skills/` directory (not code execution), then tested in an isolated scratch directory (cleaned up afterward, no pollution of the actual project) rather than the real repo, to avoid any risk of the install overwriting or interfering with `clawhub/deal-scout/SKILL.md`. `clawhub install deal-scout` succeeded — "Installed deal-scout v1.0.0" — and produced `skills/deal-scout/{SKILL.md, skill-card.md, _meta.json, .clawhub/origin.json}` plus a top-level `.clawhub/lock.json`.

Verified content integrity by diffing the installed `SKILL.md` against the source in the repo — byte-for-byte identical. Checked `origin.json` (registry, slug, owner `asmaiqbal01`, version `1.0.0`, a fingerprint) and `_meta.json` (ownerId, publishedAt) for correct provenance tracking. Noted ClawHub auto-generates a `skill-card.md` on install — a risk/use-case summary derived from the SKILL.md content, correctly surfacing the Gmail/HubSpot credential-handling risk, the localhost-binding requirement, and the approval-gated email-send flow as risks with mitigations, which reads as accurate to the actual project. Confirmed registration via `clawhub list` (`deal-scout 1.0.0`). Flagged one unresolved observation to the user rather than silently dropping it: the `fingerprint` value in `origin.json` differed from the one shown during the earlier publish dry-run, despite the file content being identical — likely two different hash scopes (bundle-level vs. single-file) rather than actual drift, but not root-caused.

## Outcome

- ✅ Impact: Confirmed the published skill is not just listed but actually installable and content-correct end-to-end — closes the loop from "published" to "usable by an installer."
- 🧪 Tests: `clawhub install deal-scout` — PASS; SKILL.md diff — PASS (identical); `clawhub list` — PASS (registered correctly).
- 📁 Files: none (test ran in a scratch directory, deleted after verification)
- 🔁 Next prompts: none pending; the fingerprint-mismatch observation is noted but not investigated further unless it becomes relevant.
- 🧠 Reflection: Testing in an isolated scratch directory rather than the real repo avoided any risk to the actual `clawhub/deal-scout/SKILL.md` from an install command with unknown overwrite behavior — worth defaulting to this pattern whenever testing an install/fetch operation for the first time.

## Evaluation notes (flywheel)

- Failure modes observed: none in the install path itself; one unexplained (but likely benign) fingerprint discrepancy between publish-dry-run and post-install origin metadata.
- Graders run and results (PASS/FAIL): content diff — PASS; registration check — PASS.
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): if it ever matters, check ClawHub docs/source for what the two fingerprint values scope to (bundle vs. file).
