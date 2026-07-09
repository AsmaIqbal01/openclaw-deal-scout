# Tasks: Gmail Intake & Deal Detection

**Input**: Design documents from `/specs/001-gmail-intake/`
**Branch**: `001-gmail-intake` | **Generated**: 2026-07-09
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Format**: `- [ ] [TaskID] [P?] [Story?] Description — file path`
- **[P]**: Can execute in parallel with other [P] tasks at the same level (touches a different file)
- **[Story]**: Which user story this task delivers toward (US1/US2/US3)
- **Sequential within a module**: Tasks on the same file are listed in dependency order

---

## Phase 1: Setup — Project Skeleton

**Purpose**: Create directory structure and configuration files. No source code yet.

- [ ] T001 Create directory tree: `src/gmail_intake/`, `tests/unit/`, `tests/integration/`, `tests/contract/`, `data/` — run `mkdir -p` from repo root
- [ ] T002 Create `pyproject.toml` at repo root with `[project]` metadata, `[project.dependencies]` (fastmcp≥2.0, google-api-python-client≥2.130, google-auth-oauthlib≥1.2, google-auth-httplib2≥0.2, google-generativeai≥0.8, portalocker≥2.8), and `[project.optional-dependencies] dev = [pytest≥8.0, pytest-asyncio]`; add `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and `testpaths = ["tests"]`
- [ ] T003 Create `.env.example` at repo root with four entries: `GMAIL_CREDENTIALS_PATH=`, `GEMINI_API_KEY=`, `STATE_STORE_PATH=./data/processed_ids.json`, `MAX_MESSAGES_PER_POLL=50`
- [ ] T004 [P] Verify `.gitignore` at repo root contains: `credentials.json`, `credentials.json.json`, `token.json`, `.env`, `data/processed_ids.json`, `data/*.lock`, `data/*.tmp` — add any missing entries
- [ ] T005 [P] Create `data/.gitkeep` (empty file so the `data/` directory is tracked by git; `processed_ids.json` itself is gitignored)

**Checkpoint**: `pip install -e ".[dev]"` runs without errors.

---

## Phase 2: Foundational — Data Contracts

**Purpose**: Define all shared dataclasses. Every subsequent module imports from here. Must be complete before Phase 3.

**⚠️ CRITICAL**: No module in Phases 3–5 can be written without this phase complete.

- [ ] T006 Create `src/gmail_intake/__init__.py` as an empty package marker
- [ ] T007 Create `src/gmail_intake/models.py` with five dataclasses exactly as specified in `specs/001-gmail-intake/data-model.md`:
  - `DealPayload` (9 fields; `deal_category` as `Literal["lead","partnership_inquiry","vendor_offer","rfq","other"]`)
  - `ProcessedMessage` (3 fields; `outcome` as `Literal` of all 7 outcome values)
  - `ClassificationRequest` (5 fields; `target_segment` defaults to `"UK micro-business, fewer than 10 employees"`)
  - `ClassificationResponse` (5 fields; all deal-specific fields `Optional`)
  - `StateStore` (2 fields; `messages` defaults to `field(default_factory=list)`)
  - Also define exceptions: `StateStoreReadError`, `ConcurrentInvocationError`, `SchemaValidationError`, `AuthError`

**Checkpoint**: `python -c "from gmail_intake.models import DealPayload, ProcessedMessage, StateStore"` succeeds.

---

## Phase 3: P1 — Unattended Deal Detection (Priority: P1) 🎯 MVP

**Goal**: A working end-to-end pipeline: poll Gmail → classify → extract basic payload → persist to state store → return `CheckNewDealsResult` dict. This phase delivers the complete US1 acceptance test.

**Independent Test** (from spec.md US1):
> Seed a test inbox with 3 deal emails and 2 non-deal emails. Invoke `check_new_deals`. Verify: exactly 3 `DealPayload` records returned, 2 "not a deal" log entries written, all 5 message IDs in `processed_ids.json`, zero errors raised.

### State Store (src/gmail_intake/state_store.py)

- [ ] T008 [US1] Create `src/gmail_intake/state_store.py` — implement `read_store(path: str) -> StateStore`:
  - If file does not exist: return `StateStore(last_poll_time=None, messages=[])` (first-run, not an error)
  - If file exists but cannot be read (permission denied, locked): log ERROR `"state store unreadable: {reason} — polling suspended"`, raise `StateStoreReadError`
  - If file exists but JSON is invalid at top level: log ERROR `"state store unreadable: invalid JSON — polling suspended"`, raise `StateStoreReadError`
  - If `last_poll_time` is present but not valid ISO 8601: log WARN `"state store: last_poll_time malformed — defaulting to 24-hour window"`, set to `None`, continue (never fatal)
- [ ] T009 [US1] Add `acquire_lock(path: str) -> portalocker.Lock` to `src/gmail_intake/state_store.py`:
  - Lock file path: `f"{path}.lock"`
  - Use `portalocker.Lock(lock_path, mode='a', flags=portalocker.LOCK_EX | portalocker.LOCK_NB)`
  - If lock cannot be acquired: log WARN `"concurrent invocation detected — aborting"`, raise `ConcurrentInvocationError`
  - Return the lock object (caller must call `lock.release()` in a finally block)
- [ ] T010 [US1] Add `append_message(path: str, store: StateStore, entry: ProcessedMessage) -> None` to `src/gmail_intake/state_store.py`:
  - Append `entry` to `store.messages` in memory
  - Write the full updated store to `f"{path}.tmp"` as JSON, then `os.rename(tmp_path, path)` (POSIX atomic)
  - If write fails (OSError): log ERROR `"state store write failed: {reason}"`, do NOT raise — continue (message will be re-evaluated next run)
- [ ] T011 [US1] Add `update_poll_time(path: str, store: StateStore, ts: str) -> None` and `check_store_size(path: str) -> None` to `src/gmail_intake/state_store.py`:
  - `update_poll_time`: set `store.last_poll_time = ts`, atomic write same as `append_message`
  - `check_store_size`: call `os.path.getsize(path)` (skip if file absent); if > 50 MB, log WARN `"state store exceeding {size:.1f} MB — archival recommended"` once per cycle

### Gmail Client (src/gmail_intake/gmail_client.py)

- [ ] T012 [P] [US1] Create `src/gmail_intake/gmail_client.py` — implement `build_service(credentials_path: str)`:
  - Derive `token_path` as `os.path.join(os.path.dirname(credentials_path), "token.json")`
  - Load `Credentials` from `token_path` using `google.oauth2.credentials.Credentials.from_authorized_user_file()`
  - If credentials expired and `refresh_token` present: call `creds.refresh(google.auth.transport.requests.Request())` — one attempt only
  - If refresh fails: log ERROR `"Gmail token refresh failed: {reason}"`, raise `AuthError`
  - Return `googleapiclient.discovery.build("gmail", "v1", credentials=creds)`
- [ ] T013 [P] [US1] Add `poll_inbox(service, since_ts: str | None, max_messages: int) -> list[dict]` to `src/gmail_intake/gmail_client.py`:
  - If `since_ts` is None: compute `after_epoch` as `int((datetime.now(UTC) - timedelta(hours=24)).timestamp())`; else parse `since_ts` to epoch
  - Call `service.users().messages().list(userId="me", q=f"after:{after_epoch} is:unread")` — paginate to collect all matching message IDs
  - For each ID fetch full message: `service.users().messages().get(userId="me", id=msg_id, format="full")`
  - Sort fetched messages by `internalDate` ascending (smallest first = oldest)
  - Apply `max_messages` cap to this sorted list BEFORE any already-processed filter (FR-003a)
  - Return the capped list of raw message dicts
  - On network error (HttpError, ConnectionError): log WARN `"network failure mid-poll: {reason}"`, raise to caller for cycle-level abort

### Classifier (src/gmail_intake/classifier.py)

- [ ] T014 [P] [US1] Create `src/gmail_intake/classifier.py` — implement `classify(request: ClassificationRequest, api_key: str) -> ClassificationResponse`:
  - Configure `genai.GenerativeModel("gemini-2.5-flash")` with `GenerationConfig(response_mime_type="application/json", response_schema={...})` exactly as in `specs/001-gmail-intake/research.md` Decision 6
  - Build prompt from template in `specs/001-gmail-intake/research.md` Decision 7 (prompt v1.0)
  - Send request; parse response JSON into `ClassificationResponse` dataclass
  - Retry loop for HTTP 429: delays 10 s / 30 s / 60 s (1 initial + 3 retries = 4 total attempts per FR-007); after retry 3 exhausted: log WARN `"classification rate-limited — skipped"`, raise `RateLimitExhaustedError`
  - For all non-429 errors (400, 500, 503, connection refused, timeout): log WARN `"classification failed: {status}/{error_type}"`, raise `ClassificationError` immediately (no retry, per FR-021)

### Extractor (src/gmail_intake/extractor.py)

- [ ] T015 [P] [US1] Create `src/gmail_intake/extractor.py` — implement `extract_metadata(msg: dict) -> dict`:
  - Parse `id`, `internalDate`, and headers (`From`, `Subject`) from raw Gmail message dict
  - `internalDate`: absent / zero / non-numeric → raise `InvalidMetadataError("internalDate")`
  - `From` header: absent / empty / no `@` in address portion → raise `InvalidMetadataError("From")`
  - `Subject` header: absent or empty → raise `InvalidMetadataError("Subject")`
  - Return dict with `gmail_message_id`, `sender_email`, `sender_name` (None if no display name), `subject`, `received_at` (ISO 8601 UTC string converted from epoch ms)
  - `sender_name`: extract display name from `From` header if present; None otherwise

### Server (src/gmail_intake/server.py)

- [ ] T016 [US1] Create `src/gmail_intake/server.py` — FastMCP server skeleton:
  - `from fastmcp import FastMCP` and `mcp = FastMCP("gmail-intake")`
  - Define helper `_get_env()` that reads all four env vars at call time (not import time); raises `EnvironmentError` for missing required vars (`GMAIL_CREDENTIALS_PATH`, `GEMINI_API_KEY`)
  - Define `async def check_new_deals_handler() -> dict` (the actual logic, separately testable)
  - Register `@mcp.tool() async def check_new_deals() -> dict` that calls `check_new_deals_handler()`
  - Add `if __name__ == "__main__": mcp.run()` entry point
- [ ] T017 [US1] Wire full pipeline in `check_new_deals_handler()` in `src/gmail_intake/server.py`:
  1. Read env vars via `_get_env()`; on `EnvironmentError`: return `{"status":"error","deals_extracted":[],"processed_count":0,"skipped_count":0,"error_details":str(e)}`
  2. `acquire_lock(state_store_path)` → on `ConcurrentInvocationError`: return `status:"error"`, `error_details:"concurrent invocation"`
  3. `read_store(state_store_path)` → on `StateStoreReadError`: release lock, return `status:"error"`
  4. `check_store_size(state_store_path)`
  5. Build `already_processed` set from `{m.gmail_message_id for m in store.messages}`
  6. `build_service(credentials_path)` → on `AuthError`: release lock, return `status:"error"`
  7. `poll_inbox(service, store.last_poll_time, max_messages)` → on network error: release lock, return `status:"error"`
  8. Per-message loop (messages not in `already_processed`):
     - Parse body (absent → `body_absent` outcome, append, continue)
     - `extract_metadata(msg)` → on `InvalidMetadataError`: `invalid_metadata` outcome, append, continue
     - Build `ClassificationRequest` from metadata + body excerpt (cap at 8,000 chars)
     - `classify(request, api_key)` → on `RateLimitExhaustedError`: `rate_limited`; on `ClassificationError`: `classification_error`; both: append, continue
     - If `not is_deal` or `confidence_score < 0.5`: `not_a_deal` outcome, append, continue
     - `extract_payload(metadata, classification)` → on `SchemaValidationError`: `schema_error`, append, continue
     - Append `deal_extracted` outcome; add to `deals_extracted` list
     - Wrap entire per-message block in bare `except Exception`: log ERROR with stack trace, write `classification_error`, continue (FR-020)
  9. `update_poll_time(state_store_path, store, utcnow_iso())` (only if no cycle-level fatal error)
  10. Release lock; return `{"status":"ok","deals_extracted":[...],"processed_count":N,"skipped_count":M,"error_details":null}`

### Phase 3 Tests

- [ ] T018 [P] [US1] Write `tests/unit/test_state_store.py`:
  - `test_read_store_missing_file()`: file absent → returns `StateStore(last_poll_time=None, messages=[])` (no error)
  - `test_read_store_corrupted_json()`: file contains `"not json{"` → raises `StateStoreReadError`
  - `test_read_store_malformed_poll_time()`: `last_poll_time="not-a-date"` → returns store with `last_poll_time=None`, no exception
  - `test_acquire_lock_conflict()`: two calls to `acquire_lock` on same path → second raises `ConcurrentInvocationError`
  - `test_append_message_atomic()`: after `append_message`, file contains the entry; no `.tmp` file left
- [ ] T019 [P] [US1] Write `tests/unit/test_classifier.py`:
  - `test_classify_429_retry_schedule()`: mock Gemini to return 429 three times then success → four total calls with 10s/30s/60s delays (mock `time.sleep`); final response is `ClassificationResponse`
  - `test_classify_429_exhausted()`: mock Gemini returns 429 four times → raises `RateLimitExhaustedError`
  - `test_classify_non_429_no_retry()`: mock Gemini returns 500 → raises `ClassificationError` after exactly 1 call (no retry)
  - `test_classify_returns_classification_response()`: mock Gemini returns valid JSON → returns correctly parsed `ClassificationResponse`

**Checkpoint**: `pytest tests/unit/test_state_store.py tests/unit/test_classifier.py -v` passes. `python -m gmail_intake.server` starts without import errors.

---

## Phase 4: P2 — Structured Deal Data Extraction (Priority: P2)

**Goal**: Harden the extraction layer — FR-011 sentence boundary rule, FR-010 word-boundary truncation, FR-009 schema validation failure with `schema_error` outcome, full field-level validation.

**Independent Test** (from spec.md US2):
> Send a known deal email. Verify: all 9 DealPayload fields populated with correct types; `deal_summary` is 1–2 sentences, ≤500 chars; `raw_email_excerpt` ≤500 chars; schema validation failure on missing required field results in `schema_error` outcome, no partial record returned.

- [ ] T020 [US2] Add `truncate_summary(text: str) -> str` to `src/gmail_intake/extractor.py` using the FR-011 regex from `specs/001-gmail-intake/research.md` Decision 8:
  - Define `_NON_SENTENCE_DOT` regex with title abbreviation exclusion list (Mr, Mrs, Ms, Dr, Prof, Sr, Jr, St, Ltd, vs, etc, eg, ie, approx, dept, Fig, No)
  - Apply `split_sentences()` → take first 2 → join
  - Apply 500-char hard cap via word-boundary truncation (sentence rule first, char cap second)
- [ ] T021 [P] [US2] Add `truncate_excerpt(text: str) -> str` to `src/gmail_intake/extractor.py`:
  - If `text` is None or empty: return None
  - If `len(text) <= 500`: return `text`
  - Else: `text[:500].rsplit(" ", 1)[0]` (truncate at nearest word boundary at or before 500 chars)
- [ ] T022 [P] [US2] Add `extract_payload(metadata: dict, classification: ClassificationResponse) -> DealPayload` to `src/gmail_intake/extractor.py`:
  - Map metadata fields to DealPayload header fields (`gmail_message_id`, `sender_email`, `sender_name`, `subject`, `received_at`)
  - Map classification fields: apply `truncate_summary()` to `deal_summary`; apply `truncate_excerpt()` to `raw_email_excerpt`
  - Validate required fields (non-empty strings; `confidence_score` in [0.0, 1.0]; `deal_category` in enum set): on any failure raise `SchemaValidationError` with field name
  - Return fully populated `DealPayload`
- [ ] T023 [P] [US2] Write `tests/unit/test_extractor.py` with FR-011 test cases from `specs/001-gmail-intake/research.md` Decision 8:
  - `test_truncate_summary_two_sentences()`: `"Hello Dr. Smith. This is a deal."` → two sentences, no split at `Dr.`
  - `test_truncate_summary_uk_acronym()`: `"We operate in the U.K. Our offer stands."` → two sentences, no split at `U.K.`
  - `test_truncate_summary_cap_at_two()`: `"Lead received. Details follow. More info later."` → `"Lead received. Details follow."`
  - `test_truncate_summary_500_char_cap()`: input where 2 sentences > 500 chars → truncated at word boundary ≤ 500
  - `test_truncate_summary_mr_jones()`: `"Mr. Jones confirmed. Ms. Lee agreed. Next steps follow."` → `"Mr. Jones confirmed. Ms. Lee agreed."`
  - `test_truncate_excerpt_under_500()`: text < 500 chars → returned unchanged
  - `test_truncate_excerpt_over_500()`: text > 500 chars → truncated at word boundary ≤ 500
  - `test_extract_payload_schema_error_missing_required()`: classification with `deal_summary=None` → raises `SchemaValidationError`
  - `test_extract_payload_confidence_out_of_range()`: `confidence_score=1.5` → raises `SchemaValidationError`
- [ ] T024 [US2] Write `tests/contract/test_tool_contract.py`:
  - Mock the full pipeline to return a known result
  - Assert `check_new_deals_handler()` return dict has exactly these keys: `status`, `deals_extracted`, `processed_count`, `skipped_count`, `error_details`
  - Assert `status` is `"ok"` or `"error"` (no other values)
  - Assert `deals_extracted` is always a list (never null)
  - Assert `processed_count == len(deals_extracted) + skipped_count` (identity relation from contracts/tool-contract.md)
  - Assert each item in `deals_extracted` has all 9 DealPayload fields with correct types

**Checkpoint**: `pytest tests/unit/test_extractor.py tests/contract/test_tool_contract.py -v` all pass.

---

## Phase 5: P3 — Idempotent Re-runs (Priority: P3)

**Goal**: Verify and test that no email ever produces a duplicate deal record or state entry across multiple invocations. The implementation (atomic writes + lock) was built in Phase 3; this phase adds tests that validate the guarantee under restart, crash, and concurrent-invocation scenarios.

**Independent Test** (from spec.md US3):
> Invoke `check_new_deals` twice on the same unchanged inbox. Verify: second invocation returns `processed_count: 0`, `deals_extracted: []`, zero new state entries for already-recorded IDs.

- [ ] T025 [US3] Write `tests/unit/test_state_store.py` additions — crash-recovery and pre-filter:
  - `test_append_message_no_tmp_on_success()`: confirm no `.tmp` file remains after successful `append_message`
  - `test_append_message_crash_recovery()`: simulate crash by leaving a `.tmp` file from a previous run; confirm `read_store` ignores `.tmp` files (they are separate from the canonical store) and returns only committed entries
  - `test_read_store_already_processed_set()`: after two `append_message` calls, `already_processed` set has exactly 2 IDs
- [ ] T026 [P] [US3] Write `tests/integration/test_check_new_deals.py`:
  - `test_idempotent_rerun()`: call `check_new_deals_handler()` twice with the same mocked Gmail response (3 messages); second call: `processed_count=0`, `deals_extracted=[]`, state store unchanged
  - `test_already_processed_pre_filter()`: seed state store with message ID X; mock Gmail returning X + 2 new messages; verify X is never passed to classifier (assert classify called exactly twice)
  - `test_concurrent_invocation_rejected()`: with lock held by a first call, second call returns `status:"error"`, `error_details:"concurrent invocation"` immediately
  - `test_process_kill_recovery()`: write two entries to state store, then invoke with same 3 messages; only the unwritten third message is classified
- [ ] T027 [US3] Add SC-005 crash scenario to `tests/integration/test_check_new_deals.py`:
  - Simulate mid-poll process kill by patching `classify` to raise `SystemExit` after first message
  - Confirm that on the next invocation: first message (already in state store) is pre-filter skipped; remaining messages are processed normally; no duplicate for first message

**Checkpoint**: `pytest tests/unit/ tests/integration/ tests/contract/ -v` all pass. Second run on same inbox produces zero new state entries.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge case hardening, operational tooling, log audit, and final validation of all 13 SC-004 boundary conditions.

- [ ] T028 [P] Create `src/gmail_intake/setup_oauth.py` — one-time offline OAuth authorisation flow:
  - Use `google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)`
  - `SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]`
  - Call `flow.run_local_server(port=0)` to open browser once; save resulting token to `token_path` via `token.to_json()`
  - Print `"Authorization complete. Token saved to {token_path}"`
  - Entry point: `if __name__ == "__main__": main()`
- [ ] T029 [P] Audit log statements across all modules against the verbosity spec in `plan.md`:
  - DEBUG: poll cycle start/end (add to server.py)
  - INFO: `check_new_deals` invoked, inbox empty (FR-003), deal classified as not_a_deal (FR-005), body absent (FR-018)
  - WARN: concurrent invocation, rate limit (FR-007, FR-017), malformed poll time, state store write failure, non-429 classifier error (FR-021), state store >50 MB
  - ERROR: credential failure (FR-016), state store read failure, network failure mid-poll, unhandled per-message exception (FR-020)
  - Verify no statement uses wrong level; fix any mismatches in `src/gmail_intake/`
- [ ] T030 [P] Verify FR-003a ordering in `src/gmail_intake/gmail_client.py`:
  - Add assertion in test: given 60 unread messages, `poll_inbox` with `max_messages=50` returns the 50 with smallest `internalDate` values, NOT the 50 most-recent
  - Confirm cap is applied before the `already_processed` filter (check `server.py` pipeline order)
- [ ] T031 Manually trigger all 13 SC-004 boundary conditions defined in `specs/001-gmail-intake/spec.md` SC-004 using unit/integration tests written in Phases 3–5; document which test covers each condition in a comment block at the top of `tests/contract/test_tool_contract.py`:
  1. Credential failure → `test_auth_error_returns_status_error` (add to integration test)
  2. Gmail rate limit → `test_gmail_rate_limit_aborts_cycle` (add to integration test)
  3. Classifier 429 exhausted → `test_classify_429_exhausted` (T019)
  4. Classifier non-429 error → `test_classify_non_429_no_retry` (T019)
  5. Schema validation failure → `test_extract_payload_schema_error_missing_required` (T023)
  6. Invalid internalDate → `test_invalid_internal_date` (add to integration test)
  7. Missing From / Subject header → `test_missing_from_header`, `test_missing_subject_header` (add to unit test)
  8. Body absent → `test_body_absent_skipped` (add to integration test)
  9. Network failure mid-poll → `test_network_failure_mid_poll` (add to integration test)
  10. Unhandled per-message exception → `test_unhandled_exception_continues` (add to integration test)
  11. State store read failure → `test_read_store_corrupted_json` (T018)
  12. State store write failure → `test_append_message_write_failure` (add to unit test)
  13. Concurrent invocation → `test_concurrent_invocation_rejected` (T026)
- [ ] T032 Run `pytest tests/ -v --tb=short` and confirm all tests pass; fix any failures before marking tasks.md complete
- [ ] T033 Run `python -m gmail_intake.server` and invoke `check_new_deals` via the MCP inspector or a direct `asyncio.run()` call against a test inbox; confirm `status:"ok"` returned with correct `deals_extracted` and state store updated

---

## Dependency Graph

```
Phase 1 (T001–T005)
    └─► Phase 2 (T006–T007)
            └─► Phase 3 (T008–T019) ── US1 MVP ──────────────────────────────┐
                    └─► Phase 4 (T020–T024) ── US2 Extraction hardening ────┐ │
                            └─► Phase 5 (T025–T027) ── US3 Idempotency ───┐ │ │
                                    └─► Phase 6 (T028–T033) ── Polish ────┘ │ │
                                                                             │ │
User story independence:                                                     │ │
  US1 independently testable after Phase 3 complete ◄────────────────────────┘ │
  US2 independently testable after Phase 4 complete ◄──────────────────────────┘
  US3 independently testable after Phase 5 complete ◄──────────────────────────
```

## Parallel Execution Opportunities

**Within Phase 3** — these tasks touch different files and can run concurrently:
```
T012 (gmail_client.py: build_service)  ──┐
T014 (classifier.py: classify)         ──┼──► T016 (server.py: skeleton)
T015 (extractor.py: extract_metadata)  ──┘         └──► T017 (server.py: wire pipeline)
T008–T011 (state_store.py)             ──┘

T018 (test_state_store.py)  ──┐  [after T008–T011]
T019 (test_classifier.py)  ──┘  [after T014]
```

**Within Phase 4** — T020, T021, T022 are additive functions to extractor.py (implement in order shown); T023 and T024 are in different test files and can be parallelised:
```
T020 → T021 → T022 (all extractor.py, sequential)
T023 (test_extractor.py) ──┐  [after T020–T022]
T024 (test_tool_contract.py) ──┘
```

**Within Phase 6** — T028, T029, T030 touch different files:
```
T028 (setup_oauth.py)    ──┐
T029 (log audit)         ──┼──► T031 (SC-004 coverage)
T030 (FR-003a ordering)  ──┘         └──► T032 (full test run) → T033 (live smoke test)
```

---

## Implementation Strategy

**MVP = Phase 3 complete** (T001–T019). This delivers:
- A working `check_new_deals` tool callable via MCP
- Gmail polling with 24-hour lookback on first run
- Gemini 2.5 Flash classification with 429 retry
- Basic DealPayload extraction (field mapping, not yet FR-011 hardened)
- State store with atomic writes and exclusive lock
- US1 acceptance test passable end-to-end

**Increment 2 = Phase 4 complete** (T020–T024): Adds FR-011 sentence rule, word-boundary truncation, schema validation failure handling. US2 acceptance test passable.

**Increment 3 = Phase 5 complete** (T025–T027): Adds formal idempotency tests. US3 acceptance test passable.

**Production-ready = Phase 6 complete** (T028–T033): OAuth setup helper, log audit, all 13 SC-004 boundary conditions verified.

---

## Task Count Summary

| Phase | Tasks | Parallel opportunities |
|---|---|---|
| Phase 1: Setup | T001–T005 (5) | T004, T005 parallel |
| Phase 2: Foundational | T006–T007 (2) | Sequential |
| Phase 3: P1 – US1 | T008–T019 (12) | T012, T014, T015 parallel; T018, T019 parallel |
| Phase 4: P2 – US2 | T020–T024 (5) | T021 parallel; T023, T024 parallel |
| Phase 5: P3 – US3 | T025–T027 (3) | T026 parallel |
| Phase 6: Polish | T028–T033 (6) | T028, T029, T030 parallel |
| **Total** | **33 tasks** | **10 parallel opportunities** |
