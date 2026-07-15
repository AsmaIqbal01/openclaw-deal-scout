---
id: "007"
title: Implement T008 read_store and T012 build_service
stage: green
date: 2026-07-10
surface: agent
model: claude-sonnet-4-6
feature: 001-gmail-intake
branch: master
user: AsmaIqbal000
command: "Implement tasks T008 and T012 from tasks.md"
labels: ["green","state-store","gmail-client","oauth","implementation"]
links:
  spec: specs/001-gmail-intake/spec.md
  ticket: null
  adr: history/adr/0002-json-file-state-store-mechanism.md
  pr: null
files:
  - src/gmail_intake/state_store.py
  - src/gmail_intake/gmail_client.py
tests:
  - "none — unit tests are T018 (state_store) and T019 (classifier)"
---

## Prompt

Implement tasks T008 and T012 from tasks.md

## Response snapshot

Created two new modules in parallel:

**T008 — `src/gmail_intake/state_store.py`**
- `read_store(path: str) -> StateStore`
- File absent → `StateStore(last_poll_time=None)` (first-run path, not an error)
- OSError → log ERROR "state store unreadable: {reason} — polling suspended", raise StateStoreReadError
- Invalid JSON or non-dict top-level → log ERROR "state store unreadable: invalid JSON — polling suspended", raise StateStoreReadError
- Malformed `last_poll_time` → log WARN "state store: last_poll_time malformed — defaulting to 24-hour window", set None, continue
- Corrupted message entry (missing key / wrong type) → log ERROR, raise StateStoreReadError
- Private helper `_is_valid_iso8601` using `datetime.fromisoformat(value.replace("Z", "+00:00"))`
- `_STORE_WARN_BYTES` constant defined (50 MB) for T011 `check_store_size()`

**T012 — `src/gmail_intake/gmail_client.py`**
- `build_service(credentials_path: str)`
- Derives `token_path = os.path.join(os.path.dirname(os.path.abspath(credentials_path)), "token.json")`
- Loads credentials via `google.oauth2.credentials.Credentials.from_authorized_user_file(token_path, SCOPES)`
- FileNotFoundError or load error → log ERROR "Gmail token refresh failed: {reason}", raise AuthError
- `creds.expired` + `creds.refresh_token` present → `creds.refresh(Request())` — one attempt
- Refresh exception → log ERROR "Gmail token refresh failed: {reason}", raise AuthError
- Returns `googleapiclient.discovery.build("gmail", "v1", credentials=creds)`

Self-review passed: correct per tasks.md, no TODOs, type-aligned with data-model.md, no secrets, readable.

## Outcome

- ✅ Impact: T008 and T012 implemented; state store read path and Gmail auth service factory complete
- 🧪 Tests: No tests in this task batch — T018 covers state_store unit tests, T019 covers classifier
- 📁 Files: 2 new files — src/gmail_intake/state_store.py, src/gmail_intake/gmail_client.py
- 🔁 Next prompts: T009 acquire_lock, T010 append_message, T011 update_poll_time/check_store_size
- 🧠 Reflection: Parallel write of both files worked cleanly; no conflicts with models.py imports

## Evaluation notes (flywheel)

- Failure modes observed: none
- Graders run and results (PASS/FAIL): self-review table — all checks PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): add T009–T011 to complete state_store.py
