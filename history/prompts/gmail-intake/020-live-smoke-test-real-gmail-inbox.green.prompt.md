---
id: 020
title: Live smoke test real Gmail inbox
stage: green
date: 2026-07-29
surface: agent
model: claude-sonnet-5
feature: 001-gmail-intake
branch: main
user: AsmaIqbal01
command: none
labels: ["smoke-test", "live", "gmail", "gemini", "env-config"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - .env
tests:
 - live invocation of check_new_deals_handler() against real Gmail inbox + real Gemini API
---

## Prompt

run a live smoke test against the real Gmail inbox

## Response snapshot

Wrote a scratchpad smoke-test script (not committed) invoking `check_new_deals_handler()` via
`asyncio.run()`, mirroring the T033 pattern from PHR 017/018. Hit two environment blockers before
it ran clean, both in `.env` (gitignored, local-only, not shared config):

1. `load_dotenv()` with no arguments searches upward from the *calling script's own directory*
   (python-dotenv's default `find_dotenv` behavior), not from cwd. Since the script lived in the
   session scratchpad temp folder, it silently loaded nothing. Fixed by passing an explicit
   `os.path.join(os.getcwd(), ".env")` path.
2. Same WSL-path-vs-native-Windows-Python issue documented in PHR 018: `GMAIL_CREDENTIALS_PATH` was
   a Unix-style absolute path (`/home/asmaiqbal01/...`) and `STATE_STORE_PATH` was a WSL-mount path
   (`/mnt/c/Users/...`) — neither resolves correctly for the native Windows `python.exe` interpreter
   that runs this project's tests. Also found that raw Bash-tool-launched Windows processes can't
   reliably resolve `\\wsl.localhost\...` UNC paths passed as literal strings (chdir/listdir failed)
   even though `os.getcwd()` reports that same UNC string when the process is launched via the
   PowerShell tool — so the smoke test needed to run through PowerShell, not Bash, for filesystem
   consistency. Changed `.env` to `GMAIL_CREDENTIALS_PATH=credentials.json` (relative to repo root)
   and `STATE_STORE_PATH=C:\Users\umzaid\AppData\Local\openclaw-deal-scout\processed_ids.json`
   (native Windows path, avoiding the portalocker-on-network-mount failure).

Re-ran via the PowerShell tool. Result:
```json
{
  "status": "ok",
  "deals_extracted": [],
  "processed_count": 0,
  "skipped_count": 0,
  "error_details": null
}
```
State store now correctly resolved at the native path, 155 total messages tracked historically.
0 new messages fetched this cycle (nothing new since `last_poll_time`), so the new STRICT REJECTION
RULES prompt change and 0.85 confidence threshold were not actually exercised against a fresh
message this run — the smoke test confirms end-to-end infra health (Gmail auth, Gemini env vars,
state store read/write, no crashes) but doesn't yet prove the new classifier behavior against live
mail.

## Outcome

- ✅ Impact: Confirmed the full pipeline (Gmail auth → poll → state store) works end-to-end against
  the real inbox after fixing two local `.env` path issues; no code changes required.
- 🧪 Tests: 1 live invocation — status=ok, count identity holds (0 == 0 + 0), no errors.
- 📁 Files: `.env` only (gitignored, local dev config — no production/shared config touched).
- 🔁 Next prompts: To actually validate the new rejection rules against live mail, need a genuinely
  new unread message matching one of the rejection patterns (newsletter/digest/unsubscribe sender)
  to arrive, then rerun this same smoke test and confirm it's skipped with outcome `not_a_deal`.
- 🧠 Reflection: `load_dotenv()`'s default search-from-caller's-file behavior is a recurring trap for
  scratchpad scripts run from outside the repo tree — always pass an explicit path. Path format
  (WSL-style vs native Windows vs UNC) must match whichever interpreter/tool actually executes the
  process; PowerShell tool and Bash tool do not share the same filesystem-resolution behavior for
  Windows binaries in this environment.

## Evaluation notes (flywheel)

- Failure modes observed: silent dotenv no-op from wrong search root; portalocker permission error
  on WSL-mounted state store path; UNC path resolution failure specific to Bash-tool-launched
  Windows processes (worked fine via PowerShell tool).
- Graders run and results (PASS/FAIL): live invocation acceptance checks — PASS (status=ok, list
  shape, count identity).
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): trigger a real inbound newsletter/digest email, rerun
  the smoke test, and inspect the state store entry's `outcome` field to confirm `not_a_deal` for
  that message.
