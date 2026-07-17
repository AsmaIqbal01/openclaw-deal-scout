# Tasks: Discord Deal Notification

**Feature**: `003-discord-notification`
**Input**: `specs/003-discord-notification/` — spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md
**Branch**: `003-discord-notification`
**Total tasks**: 29 (T001–T029)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no same-file dependency)
- **[Story]**: Maps to user story — US1 (alert delivery), US2 (idempotency), US3 (failure/pending), US4 (swappable notifier)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `discord_notifier` package skeleton. No new dependencies —
`requests`, `portalocker`, and `fastmcp` are already in `pyproject.toml`.

- [x] T001 Create empty package marker `src/discord_notifier/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core exceptions, types, and state store functions that every user
story depends on. Must be complete before any US phase begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Create `src/discord_notifier/models.py` with: `DiscordWebhookError(status_code: int, body: str)`, `DiscordRateLimitError(DiscordWebhookError)` (include `retry_after: float` attr), `DiscordTimeoutError(Exception)`, `NotifyOutcome = Literal["discord-notified", "crm-logged-notify-pending", "skipped"]`, `@dataclass NotificationCycleResult(status: str, discord_notified: int = 0, notify_pending: int = 0, skipped: int = 0, error_details: str | None = None)`

- [x] T003 Create `src/discord_notifier/state_store.py` with five functions using the same atomic merge-write (`NamedTemporaryFile` + `os.replace`) and `portalocker` locking pattern as `src/crm_logger/state_store.py`:
  - `_raw_load(path: str) -> dict` — returns `{"last_poll_time": None, "messages": []}` if file absent
  - `_merge_write(path: str, updates: dict) -> None` — reads existing JSON, merges updates, writes atomically
  - `read_notify_store(path: str) -> dict` — returns raw JSON dict (all fields preserved)
  - `get_ready_to_notify(store: dict) -> list[dict]` — filters entries where `status == "crm-logged"`
  - `get_pending_notifications(store: dict) -> list[dict]` — filters entries where `status == "crm-logged-notify-pending"`
  - `write_notify_outcome(path: str, gmail_message_id: str, outcome: str, **extra_fields) -> None` — merge-writes `status = outcome` plus any `extra_fields` (e.g. `notified_at`, `notify_error_reason`) onto the matching message entry

- [x] T004 [P] Write `tests/unit/test_notify_state_store.py` with 11 tests:
  1. `_raw_load` on absent file → returns default skeleton
  2. `_raw_load` on valid JSON → returns parsed dict
  3. `read_notify_store` preserves all top-level keys (including `consecutive_401_cycles`)
  4. `get_ready_to_notify` returns only entries with `status == "crm-logged"`, not `crm-logged-notify-pending` or `discord-notified`
  5. `get_pending_notifications` returns only entries with `status == "crm-logged-notify-pending"`
  6. `get_ready_to_notify` on empty store → empty list
  7. `get_pending_notifications` on empty store → empty list
  8. `write_notify_outcome` with `outcome="discord-notified"` and `notified_at` extra field → entry updated, all other entries preserved
  9. `write_notify_outcome` with `outcome="crm-logged-notify-pending"` and `notify_error_reason` → entry updated
  10. `_merge_write` preserves `consecutive_401_cycles` top-level key written by `crm_logger`
  11. `write_notify_outcome` on non-existent `gmail_message_id` → raises `KeyError` (entry must already exist in store)

**Checkpoint**: Foundation ready — all US phases can now begin.

---

## Phase 3: User Story 1 — Alert Operator When a New Deal Lands (Priority: P1) 🎯 MVP

**Goal**: Full end-to-end delivery path: read `crm-logged` entries from state
store → format Discord embed → POST to webhook → write `discord-notified` to
state store → return `NotificationCycleResult`.

**Independent Test**: Seed state store with one `crm-logged` entry. Call
`sync_notifications()` (or `run_notify_cycle()`). Verify: Discord embed received
by channel, state updated to `discord-notified`, cycle result shows
`discord_notified=1`.

- [x] T005 [P] [US1] Create `src/discord_notifier/formatter.py` with `format_embed(deal: dict) -> dict`:
  - `title`: `deal["subject"]` truncated to 253 chars + `"..."` if over 256 (defensive — Step 2 already caps at 255 but formatter is authoritative)
  - `description`: `deal["deal_summary"]` if non-empty else `"(no summary)"`
  - `fields[0]`: name=`"From"`, value=`f'{deal["sender_name"]} <{deal["sender_email"]}>'` when `sender_name` is non-null, else `deal["sender_email"]` alone; `inline=True`
  - `fields[1]`: name=`"Category"`, value=`deal["deal_category"]`; `inline=True`
  - `fields[2]`: name=`"Confidence"`, value=`f"{round(deal['confidence_score'] * 100)}%"`; `inline=True`
  - Returns dict: `{"embeds": [{"title": ..., "description": ..., "fields": [...]}]}`

- [x] T006 [P] [US1] Write `tests/unit/test_notify_formatter.py` with 7 tests:
  1. Happy path: all fields present → correct embed structure and field values
  2. `sender_name=None` → `"From"` value is email only (no `<None>` or empty string)
  3. `deal_summary=""` (empty string) → description is `"(no summary)"`
  4. Subject exactly 256 chars → no truncation (256 is at the limit; Discord allows ≤ 256)
  5. Subject 257 chars → truncated to 253 + `"..."`  (result is 256 chars)
  6. `confidence_score=0.875` → `"88%"` (rounded)
  7. `confidence_score=0.0` → `"0%"`

- [x] T007 [US1] Create `src/discord_notifier/adapter.py` with four exports:
  - `class NotifierContract(Protocol)`: `def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]`
  - `class DiscordAdapter`: `__init__(self, webhook_url: str, timeout: tuple[int,int] = (5, 10))` — raises `EnvironmentError` if `webhook_url` is empty/None; `notify(self, deal: dict) -> Literal[...]` calls `format_embed(deal)`, `requests.post(webhook_url, json=embed, timeout=(5,10))`; HTTP 2xx → `"discord-notified"`; HTTP 429 → logs `[WARN] Discord rate limited (retry_after=N)`, reads `retry_after` from response JSON body → returns `"crm-logged-notify-pending"`; HTTP 4xx/5xx → logs WARN → returns `"crm-logged-notify-pending"`; `requests.exceptions.Timeout` → `"crm-logged-notify-pending"`; any other exception → `"crm-logged-notify-pending"`; **never raises**
  - `class NoopAdapter`: `notify(self, deal: dict) -> Literal[...]` always returns `"discord-notified"`
  - `def get_adapter(notifier: str | None, env: dict) -> NotifierContract`: raises `EnvironmentError` if `notifier` is None/empty; raises `EnvironmentError` if `notifier` is unknown; for `"discord"` reads `env.get("DISCORD_WEBHOOK_URL")` and raises `EnvironmentError` if missing; for `"noop"` returns `NoopAdapter()`

- [x] T008 [US1] Write `tests/unit/test_discord_adapter.py` with 13 tests (mock `requests.post` with `unittest.mock.patch`):
  1. HTTP 200 → `"discord-notified"`
  2. HTTP 204 → `"discord-notified"`
  3. HTTP 429 with `{"retry_after": 2.5}` body → `"crm-logged-notify-pending"` + WARN log
  4. HTTP 400 → `"crm-logged-notify-pending"` + WARN log
  5. HTTP 500 → `"crm-logged-notify-pending"` + WARN log
  6. `requests.exceptions.Timeout` raised → `"crm-logged-notify-pending"` + WARN log
  7. `requests.exceptions.ConnectionError` raised → `"crm-logged-notify-pending"` + WARN log
  8. Empty `webhook_url` → `EnvironmentError` at `__init__`
  9. `get_adapter("discord", env_with_url)` → returns `DiscordAdapter` instance
  10. `get_adapter("noop", {})` → returns `NoopAdapter` instance
  11. `get_adapter(None, {})` → `EnvironmentError`
  12. `get_adapter("slack", {})` → `EnvironmentError` (unrecognised adapter)
  13. `get_adapter("discord", {})` (no `DISCORD_WEBHOOK_URL`) → `EnvironmentError`

- [x] T009 [US1] Create `src/discord_notifier/notifier.py` with `notify_deal(deal: dict, adapter: NotifierContract, state_path: str) -> NotifyOutcome`:
  1. If `deal.get("status") == "discord-notified"` → log DEBUG, return `"skipped"` immediately (no API call)
  2. Call `outcome = adapter.notify(deal)`
  3. If `outcome == "discord-notified"`: attempt `write_notify_outcome(state_path, gmail_message_id, "discord-notified", notified_at=_utcnow_iso())`; on `OSError` from write → log `[ERROR] State write failed after successful Discord delivery for <id>` → still return `"discord-notified"` (delivery happened; state will be retried next cycle since status stays `crm-logged`)
  4. If `outcome == "crm-logged-notify-pending"`: call `write_notify_outcome(state_path, gmail_message_id, "crm-logged-notify-pending", notify_error_reason=<error_str>)`
  5. Return `outcome`

- [x] T010 [US1] Write `tests/unit/test_notifier.py` with 5 US1 tests:
  1. Deal with `status="crm-logged"`, `NoopAdapter` → outcome `"discord-notified"`, state written with `notified_at`
  2. `notify_deal` called twice on same deal (second call: `status="discord-notified"`) → second call returns `"skipped"`, no adapter call
  3. Adapter returns `"discord-notified"` but `write_notify_outcome` raises `OSError` → function returns `"discord-notified"` (delivery logged, state unchanged)
  4. Adapter returns `"crm-logged-notify-pending"` → `write_notify_outcome` called with `outcome="crm-logged-notify-pending"` and `notify_error_reason` populated
  5. `notify_deal` with all 9 DealPayload fields present → adapter receives full deal dict (no fields stripped)

- [x] T011 [US1] Create `src/discord_notifier/orchestrator.py` with `run_notify_cycle(state_path: str, *, notifier_name: str | None = None, env: dict | None = None) -> NotificationCycleResult`:
  1. Resolve `notifier_name` from `env.get("NOTIFIER")` if not passed; call `get_adapter(notifier_name, env)` — on `EnvironmentError` return `NotificationCycleResult(status="error", error_details=str(exc))`
  2. Acquire portalocker lock on `state_path`; on `ConcurrentInvocationError` return `NotificationCycleResult(status="error", error_details="concurrent invocation")`
  3. Call `read_notify_store(state_path)`; on `FileNotFoundError` or `json.JSONDecodeError` → release lock, return `NotificationCycleResult(status="error", error_details="State store ...")`
  4. Build ordered work list: `get_pending_notifications(store)` first, then `get_ready_to_notify(store)` (drain-first)
  5. For each deal: call `notify_deal(deal, adapter, state_path)`; accumulate counts in `NotificationCycleResult`; catch any unhandled exception per deal → log `[ERROR]`, mark pending, continue
  6. Release lock
  7. Return `NotificationCycleResult(status="ok", ...)`

- [x] T012 [US1] Write `tests/unit/test_notify_orchestrator.py` with 5 US1 tests:
  1. One `crm-logged` deal, `NoopAdapter` → result `status="ok"`, `discord_notified=1`
  2. Empty store (no deals) → result `status="ok"`, all counts 0
  3. Missing `NOTIFIER` env var → result `status="error"`, `error_details` contains "NOTIFIER"
  4. State store file absent → result `status="error"`, `error_details` contains "State store"
  5. State store valid JSON but root is array → `json.JSONDecodeError` equivalent → result `status="error"`

- [x] T013 [US1] Create `src/discord_notifier/server.py`:
  - `mcp = FastMCP("discord-notifier")`
  - `@mcp.tool() def sync_notifications() -> dict:` reads `NOTIFIER`, `STATE_STORE_PATH`, calls `run_notify_cycle(state_path, env=os.environ)`; wraps any unhandled exception in `NotificationCycleResult(status="error", error_details=f"{type(exc).__name__}")` (no raw detail leak); returns `dataclasses.asdict(result)`
  - `if __name__ == "__main__": mcp.run()`

**Checkpoint**: US1 complete — `sync_notifications()` delivers a `crm-logged` deal to Discord and writes `discord-notified` to the state store.

---

## Phase 4: User Story 2 — Idempotent Re-run (Priority: P2)

**Goal**: Prove that calling `sync_notifications()` on an already-`discord-notified`
deal is a strict no-op — no Discord API call, no state mutation, `skipped` count
incremented.

**Independent Test**: Set deal to `discord-notified`. Call `sync_notifications()`.
Verify `skipped=1`, `discord_notified=0`, `notify_pending=0`, no Discord API call.

- [x] T014 [US2] Extend `tests/unit/test_notifier.py` with 3 US2 idempotency tests:
  1. Deal `status="discord-notified"` → `notify_deal` returns `"skipped"`, adapter NOT called (use `MagicMock` to assert `adapter.notify.call_count == 0`)
  2. Deal `status="discord-notified"` → state store NOT written (assert `write_notify_outcome` not called)
  3. Deal `status="discord-notified"`, `notified_at` already set → `notified_at` unchanged after call

- [x] T015 [US2] Extend `tests/unit/test_notify_orchestrator.py` with 3 US2 tests:
  1. Three deals: 1 `discord-notified`, 1 `crm-logged`, 1 `crm-logged-notify-pending` → result `discord_notified=1`, `notify_pending=0`, `skipped=1` (pending → notified by NoopAdapter, new → notified, already-notified → skipped)
  2. All deals `discord-notified` → result `status="ok"`, `skipped=3`, all other counts 0
  3. Call `run_notify_cycle` twice on same store; second call sees all `discord-notified` → `skipped` count equals first call's `discord_notified` count

**Checkpoint**: US2 complete — idempotent re-run verified at both `notify_deal` and `run_notify_cycle` layers.

---

## Phase 5: User Story 3 — Retryable Pending State on Discord Failure (Priority: P3)

**Goal**: Prove that Discord API failures leave the deal in `crm-logged-notify-pending`
(never silently dropped, never falsely marked notified), and that drain-first
ordering retries pending deals before new ones.

**Independent Test**: Set deal to `crm-logged`. Configure `DiscordAdapter` to fail
(bad URL). Call `sync_notifications()`. Verify `notify_pending=1`, entry is
`crm-logged-notify-pending`, `notify_error_reason` populated, `notified_at` absent.
Then fix URL and call again — verify deal retried and `discord-notified`.

- [x] T016 [US3] Extend `tests/unit/test_discord_adapter.py` with 3 US3 failure-path tests:
  1. `requests.post` raises `ConnectionError` (bad URL/revoked webhook) → `"crm-logged-notify-pending"`, WARN logged, no exception propagated
  2. HTTP 400 (embed validation error) → `"crm-logged-notify-pending"`, WARN logged
  3. HTTP 503 → `"crm-logged-notify-pending"`, WARN logged

- [x] T017 [US3] Extend `tests/unit/test_notifier.py` with 4 US3 tests:
  1. Adapter returns `"crm-logged-notify-pending"` → `write_notify_outcome` called with `outcome="crm-logged-notify-pending"` and `notify_error_reason` non-empty
  2. Adapter returns `"discord-notified"` but `write_notify_outcome` raises `OSError` → function returns `"discord-notified"` AND logs `[ERROR] State write failed after successful Discord delivery for <id>` (FR-016 path)
  3. `notify_error_reason` is truncated to max 255 chars when the failure detail is long
  4. `notified_at` is NOT written when outcome is `"crm-logged-notify-pending"`

- [x] T018 [US3] Extend `tests/unit/test_notify_orchestrator.py` with 5 US3 tests:
  1. One `crm-logged-notify-pending` deal + one `crm-logged` deal, both succeed with `NoopAdapter` → `discord_notified=2`; verify pending entry processed BEFORE new entry (drain-first: assert call order via mock)
  2. One `crm-logged` deal, adapter fails → result `notify_pending=1`, `discord_notified=0`, `status="ok"` (cycle-level is still ok; only per-deal failure)
  3. Two `crm-logged` deals, first fails, second succeeds → `discord_notified=1`, `notify_pending=1`, `status="ok"` (per-deal isolation — one failure doesn't abort cycle)
  4. State store readable but contains `{"messages": "not-a-list"}` (structurally invalid) → graceful error, `status="error"`
  5. State store readable but invalid JSON → `status="error"`, `error_details` contains "parse failed"

- [x] T019 [US3] Add concurrent invocation test to `tests/unit/test_notify_orchestrator.py`:
  - Mock portalocker to raise `ConcurrentInvocationError` → result `status="error"`, `error_details="concurrent invocation"`, `discord_notified=0`

**Checkpoint**: US3 complete — all failure modes proven retryable, drain-first ordering verified.

---

## Phase 6: User Story 4 — Swappable Notifier Contract (Priority: P4)

**Goal**: Prove the `NotifierContract` Protocol is real — a minimal `NoopAdapter`
satisfies it without importing the Protocol, `NOTIFIER=noop` activates it via
`get_adapter()`, and changing `NOTIFIER` requires zero changes to `notifier.py`,
`orchestrator.py`, `server.py`, `state_store.py`, or `formatter.py`.

**Independent Test**: Create a one-method class `class CountingAdapter` with
`notify(self, deal)` that counts calls and returns `"discord-notified"`. Pass it
to `notify_deal()`. Verify it works without inheriting from any base class and
without importing `NotifierContract`.

- [x] T020 [US4] Extend `tests/unit/test_discord_adapter.py` with 5 US4 adapter contract tests:
  1. `NoopAdapter().notify(any_deal)` always returns `"discord-notified"` regardless of deal content
  2. A plain class with a `notify` method (no import of `NotifierContract`) satisfies duck-typing when passed to `notify_deal()` — Protocol is structural only
  3. `get_adapter("noop", {})` → returns instance whose `notify` returns `"discord-notified"` (NoopAdapter)
  4. `get_adapter("discord", env_with_url)` → returns `DiscordAdapter` instance; webhook URL set correctly
  5. Registering a second known adapter in `get_adapter` requires changing only `adapter.py` — no other files — (self-documenting test: call `get_adapter("noop", {})` from `run_notify_cycle` to confirm server.py and orchestrator.py are unmodified)

- [x] T021 [US4] Add `NOTIFIER` env-var resolution test to `tests/unit/test_notify_orchestrator.py`:
  - `run_notify_cycle` with `env={"NOTIFIER": "noop", "STATE_STORE_PATH": "..."}` → uses `NoopAdapter`, does not raise, `discord_notified` count matches deal count

**Checkpoint**: US4 complete — swappable notifier contract verified as duck-typed and config-driven.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T022 Add `models.py` import-cycle guard — verify `from discord_notifier.models import NotificationCycleResult` works from a cold Python process (no circular imports between adapter, notifier, orchestrator, server)

- [x] T023 Run `~/.local/bin/pytest tests/unit/test_notify_state_store.py tests/unit/test_notify_formatter.py tests/unit/test_discord_adapter.py tests/unit/test_notifier.py tests/unit/test_notify_orchestrator.py -v --tb=short` and confirm all pass with zero failures

- [x] T024 Run full regression suite `~/.local/bin/pytest tests/ --tb=short -q` to confirm zero regressions in `001-gmail-intake` and `002-crm-logger` tests (state store merge-write changes are backward-compatible)

- [ ] T025 Smoke test with `NOTIFIER=noop` (manual — requires live shell): seed `data/test_processed_ids.json` with one `crm-logged` entry, run `NOTIFIER=noop STATE_STORE_PATH=data/test_processed_ids.json python3.12 -m discord_notifier.server` and call `sync_notifications` via MCP; verify state entry updated to `discord-notified` and result `discord_notified=1`

- [x] T026 Write integration test skeleton `tests/integration/test_sync_notifications.py` with 5 test scenarios from quickstart.md (Scenarios 1–5); gate entire file with `pytest.importorskip` or `pytest.mark.skipif` on `DISCORD_WEBHOOK_URL` env var absent so test is skipped in CI without a real webhook

- [x] T027 Verify `specs/003-discord-notification/tasks.md` task markers: update this file — mark all completed tasks `[x]` as each is implemented per the `/sp.implement` contract

- [x] T028 [P] Confirm `DISCORD_WEBHOOK_URL` and `NOTIFIER` are documented in the project's `.env.example` or `README` env-var reference (do not commit `.env`)

- [ ] T029 [P] Add `discord-notifier` server entry to claude_desktop_config.json (manual — requires Claude Desktop restart): pointing to `python3.12 -m discord_notifier.server` — check config file used by the OpenClaw agent (same pattern as `gmail-intake` and `crm-logger` entries)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all US phases
- **Phase 3 (US1)**: Depends on Phase 2 completion
- **Phase 4 (US2)**: Depends on Phase 3 (T009 `notify_deal` must exist; US2 tests extend it)
- **Phase 5 (US3)**: Depends on Phase 3 (US3 failure tests extend US1 code paths)
- **Phase 6 (US4)**: Depends on Phase 3 (US4 tests verify adapter.py from Phase 3)
- **Phase 7 (Polish)**: Depends on Phases 3–6 all complete

### User Story Dependencies

```
Phase 1 Setup
    ↓
Phase 2 Foundational (T002 models.py, T003 state_store.py, T004 tests)
    ↓
Phase 3 US1 (formatter → adapter → notifier → orchestrator → server + tests)
    ↓ ↓ ↓
   US2  US3  US4  ← all extend Phase 3 code; can proceed in parallel with each other
    ↓ ↓ ↓
Phase 7 Polish
```

### Within Phase 3 (US1)

- T005 (formatter) and T006 (formatter tests) are parallel — different files, no deps
- T007 (adapter) depends on T005 (formatter called from `DiscordAdapter.notify`)
- T008 (adapter tests) depends on T007
- T009 (notifier) depends on T007 (adapter) and T003 (state_store)
- T010 (notifier tests) depends on T009
- T011 (orchestrator) depends on T009 (notifier) and T003 (state_store)
- T012 (orchestrator tests) depends on T011
- T013 (server) depends on T011 (orchestrator)

### Parallel Opportunities

- T004 (state_store tests) can run in parallel with T005+T006 (formatter + formatter tests)
- T005 and T006 are parallel with each other
- Phases 4, 5, 6 can proceed in parallel once Phase 3 is complete

---

## Parallel Example: Phase 3 (US1) Execution

```bash
# Step 1: Run in parallel (different files, no deps between them)
T005: Create src/discord_notifier/formatter.py
T006: Write tests/unit/test_notify_formatter.py

# Step 2: After T005 completes (adapter imports formatter)
T007: Create src/discord_notifier/adapter.py
T008: Write tests/unit/test_discord_adapter.py  # parallel with T007 once interface known

# Step 3: After T007 completes
T009: Create src/discord_notifier/notifier.py
T010: Write tests/unit/test_notifier.py  # parallel with T009 once signature known

# Step 4: After T009 completes
T011: Create src/discord_notifier/orchestrator.py
T012: Write tests/unit/test_notify_orchestrator.py

# Step 5: After T011 completes
T013: Create src/discord_notifier/server.py
```

---

## Implementation Strategy

### MVP (Phase 1 + 2 + 3 only — 13 tasks)

1. Complete Phase 1 (1 task): package skeleton
2. Complete Phase 2 (3 tasks): models + state_store + tests
3. Complete Phase 3 (9 tasks): formatter → adapter → notifier → orchestrator → server + tests
4. **STOP AND VALIDATE**: Run `pytest tests/unit/ -v`, smoke test with NOTIFIER=noop
5. Deliver US1 — operators get Discord alerts for `crm-logged` deals

### Full Delivery (All 29 tasks, Phases 1–7)

1. MVP (Phase 1–3) → validate
2. Phase 4 (US2): idempotency tests → validate
3. Phase 5 (US3): failure/pending tests → validate
4. Phase 6 (US4): swappable contract tests → validate
5. Phase 7 (Polish): integration test, smoke test, regression check
6. Each phase adds tests proving the constitutional guarantees (IV, V, VI)

---

## Notes

- All test files for a given module live at `tests/unit/test_<module_name>.py`
- Tests added in Phases 4–6 extend existing test files (not new files) — use `append` approach
- The `discord_notifier` package is auto-discovered by `pyproject.toml`'s `find` config; no `pyproject.toml` changes needed
- State store merge-write MUST preserve `consecutive_401_cycles` and all `crm_logger` fields — verified by T004 test 10
- `notify_error_reason` (Discord) must not collide with `error_reason` (CRM) — both are separate keys in the JSON entry
- Never commit `DISCORD_WEBHOOK_URL` to version control; only in `.env`
