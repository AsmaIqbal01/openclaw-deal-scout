---
id: 008
title: Verify deal-scout showing in ClawHub search
stage: general
date: 2026-07-28
surface: agent
model: claude-sonnet-5
feature: none
branch: main
user: AsmaIqbal01
command: none
labels: ["clawhub", "publishing", "verification"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files: []
tests:
 - clawhub search "deal scout" --limit 20 (via WSL Ubuntu-22.04, authenticated session)
 - clawhub search "openclaw gmail hubspot deal pipeline" --limit 20
 - clawhub inspect deal-scout --json
---

## Prompt

verify it's showing up in ClawHub search

create a PHR for this

## Response snapshot

Ran `clawhub search "deal scout"` through the WSL Ubuntu-22.04 shell (the environment with the authenticated ClawHub session, per the prior publish session). An initial attempt with `--json` failed since `search` doesn't support that flag; retried plain-text. First `--limit`-less search returned only two unrelated pre-existing skills (`audible-goodreads-deal-scout`, `vc-ai-infra-scout`) — `deal-scout` wasn't appearing yet, consistent with the "pending.publication" moderation status seen right after publish. Re-ran with `--limit 20` (this run took long enough to move to a background task; retrieved via `TaskOutput`) and confirmed `deal-scout` now ranks as the top result, ahead of the two unrelated skills. Cross-checked with `clawhub inspect deal-scout --json` for the full public record: owner correctly attributed to `@asmaiqbal01` (Asma Iqbal), version `1.0.0` under license `MIT-0`, moderation `verdict: "clean"` / `legacyReason: "scanner.llm.clean"` (upgraded from the earlier `pending.publication` state — confirming the automated security scan had completed), and an auto-generated changelog summarizing the pipeline accurately from the SKILL.md content.

## Outcome

- ✅ Impact: Confirmed the `deal-scout` skill is publicly discoverable via ClawHub's vector search and fully indexed/scanned — publish is complete end-to-end, not just accepted by the CLI.
- 🧪 Tests: `clawhub search "deal scout" --limit 20` — PASS (deal-scout top result); `clawhub inspect deal-scout --json` — PASS (owner, version, clean moderation verdict all correct).
- 📁 Files: none (verification only, no files changed)
- 🔁 Next prompts: none pending.
- 🧠 Reflection: Moderation/indexing state (`pending.publication` → `scanner.llm.clean`) lagged the CLI's "published" response by roughly the gap between the publish command and this verification — worth remembering that a "published" status doesn't guarantee immediate search visibility.

## Evaluation notes (flywheel)

- Failure modes observed: `clawhub search` has no `--json` flag (unlike `skill publish`/`inspect`) — plain-text output only.
- Graders run and results (PASS/FAIL): search ranking — PASS; inspect metadata — PASS.
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
