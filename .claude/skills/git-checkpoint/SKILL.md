---
name: git-checkpoint
description: >
  Commit and push the current milestone to GitHub (origin/main) after
  confirming no secrets are staged. Follows a strict pre-commit secret scan,
  shows a staged-file manifest for human approval, then commits with a
  milestone-scoped message and pushes. Use when asked to "checkpoint",
  "commit this milestone", or "push to main".
tools:
  - Bash
  - Read
  - Grep
---

# SKILL: git-checkpoint

A milestone commit procedure for the OpenClaw Deal Scout project.
Target: remote `origin`, branch `main`. Never force-push. Never skip the
secret scan.

---

## Step 1 — Capture current state

Run these three commands and display all output to the user before proceeding:

```bash
git status
```

```bash
git diff --stat HEAD
```

```bash
git diff --cached --stat
```

If `git status` shows "nothing to commit, working tree clean", report:
> No changes to commit. Working tree is clean. Checkpoint skipped.
and stop here.

---

## Step 2 — Secret scan (MANDATORY — never skip)

Scan every file that `git status` lists as modified, untracked, or staged.
Check for the following patterns using Grep (not bash grep):

| Pattern | What it catches |
|---|---|
| `sk-[A-Za-z0-9]{20,}` | OpenAI / generic secret keys |
| `ghp_[A-Za-z0-9]{36}` | GitHub personal access tokens |
| `AIza[A-Za-z0-9_-]{35}` | Google API keys (Gemini, Maps, etc.) |
| `Bearer [A-Za-z0-9\-._~+/]+=*` | Bearer tokens in any file |
| `discord\.com/api/webhooks/` | Discord webhook URLs |
| `(HUBSPOT|hubspot).*[Kk]ey` | HubSpot private-app or service keys |
| `refresh_token` | OAuth refresh tokens |
| `client_secret` | OAuth client secrets |
| `private_key` | Private key material |
| `password\s*=\s*\S+` | Inline password assignments |

Also flag any file whose name matches:
- `.env` or `.env.*` (any variant)
- `*token*.json`, `*credential*.json`, `*secret*.json`
- `oauth2*.json`, `gmail-token*`, `token.json`

### Secret scan result format

Present findings as one of two outcomes:

**CLEAN** — no matches found:
```
✅ Secret scan CLEAN — no credential patterns detected in changed files.
```

**BLOCKED** — one or more matches found:
```
🚨 Secret scan BLOCKED — do NOT stage or commit until resolved.

Flagged files:
  - <file> : <matched pattern>
  - ...

Required action before checkpoint can proceed:
  1. Remove the secret from the file (or move it to .env).
  2. Verify .env and credential files are listed in .gitignore.
  3. Re-run /git-checkpoint.
```

If BLOCKED: stop immediately. Do not stage, commit, or push anything.

---

## Step 3 — Build the staged-file manifest

Collect the full list of files that WILL be staged (all modified and untracked
files that are NOT blocked by Step 2). Present it to the user as:

```
Files to be staged and committed:
  ✅  <relative-path>       <short description of what changed>
  ✅  <relative-path>       <short description of what changed>
  ...
  ⛔  <relative-path>       EXCLUDED — flagged in secret scan
  ⛔  .env                  EXCLUDED — credential file, never committed
```

Use `git diff --stat` output and `git status` to derive the short descriptions
(e.g., "modified", "new file", "renamed"). Keep descriptions to 5 words max.

---

## Step 4 — Human approval gate

**Always pause here.** Output exactly:

```
📋 Milestone checkpoint ready.

Milestone label (from your message or context): <inferred label>
Branch: main → origin/main
Files to stage: <count>

Approve? Reply "yes" to commit and push, or tell me what to adjust.
```

Do NOT proceed to Step 5 until the user explicitly confirms. Acceptable
confirmations: "yes", "go", "approved", "looks good", "commit it", "push it".
Any other reply means adjust and re-present the manifest.

---

## Step 5 — Stage, commit, and push

Once approved:

**5a. Stage only the approved files** (never use `git add .` or `git add -A`):

```bash
git add <file1> <file2> ...   # list each file explicitly
```

Run `git status` after staging and confirm only intended files appear under
"Changes to be committed". If anything unexpected is staged, unstage it with
`git restore --staged <file>` and re-confirm with the user.

**5b. Commit with a milestone-scoped message.**

Derive the message from:
1. The milestone label the user provided (e.g., "subagent created",
   "spec locked", "plan generated", "implementation done").
2. The list of changed files (summarise in ≤5 words).

Message format:
```
<milestone-label>: <brief summary of changes>

Files: <count> changed
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Pass via heredoc to avoid quoting issues:
```bash
git commit -m "$(cat <<'EOF'
<milestone-label>: <brief summary>

Files: N changed
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

**5c. Push to origin/main:**

```bash
git push origin main
```

If the push is rejected (non-fast-forward), do NOT force-push. Instead:
```
⚠️  Push rejected — remote has commits not in your local branch.
Run `git pull --rebase origin main` first, resolve any conflicts, then
re-run /git-checkpoint.
```

---

## Step 6 — Report

After a successful push, output:

```
✅ Checkpoint committed and pushed.

  Commit: <short SHA from git rev-parse --short HEAD>
  Branch: main → origin/main
  Milestone: <label>
  Files committed: <count>

Next milestone: <inferred from context, or "ask user">
```

If any step failed, output the exact error and a specific corrective action.
Never fail silently.

---

## Invariants (never violate these)

- NEVER stage `.env`, `*.json` credential files, or any file flagged in Step 2.
- NEVER use `git add .` or `git add -A`.
- NEVER force-push (`--force`, `-f`) to any branch.
- NEVER skip the human approval gate in Step 4.
- NEVER amend a commit that has already been pushed.
- NEVER commit if the secret scan returned BLOCKED.
