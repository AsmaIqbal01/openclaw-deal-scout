# Tasks: HubSpot CRM Logger

**Input**: Design documents from `specs/002-hubspot-crm-logger/`
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅ · quickstart.md ✅

**Tests**: Included — User Story 5 acceptance criteria explicitly call for unit tests; consistent with 001-gmail-intake TDD conventions.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency)
- **[Story]**: Which user story this task belongs to (US1–US5 from spec.md)
- Exact file paths are given in every description

## Path Conventions

Single project: `src/`, `tests/` at repository root. New package: `src/crm_logger/`. Cross-feature changes: `src/gmail_intake/`.

---

## Phase 1: Setup

**Purpose**: Package scaffold and dependency registration before any implementation begins.

- [x] T001 Create `src/crm_logger/__init__.py` (empty file to make it a Python package)
- [x] T002 [P] Add `requests>=2.31` to `requirements.txt` (or `pyproject.toml` `[project.dependencies]`) — new dependency for HubSpot REST calls
- [x] T003 [P] Create empty stub test files: `tests/unit/test_hubspot_client.py`, `tests/unit/test_log_deal.py`, `tests/unit/test_orchestrator.py`, `tests/unit/test_crm_state_store.py` (each with a single `pass` body so pytest collects them without error)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models, state store, and client skeleton that ALL user story phases depend on.

**⚠️ CRITICAL**: No user story work can begin until T004 and T005 are complete. T006–T008 can start as soon as T004 is done.

- [x] T004 Create `src/crm_logger/models.py` with all dataclasses and exceptions per `data-model.md`: `CrmStateStore`, `HubSpotContact`, `HubSpotDeal`, `HubSpotWriteResult`, `CrmCycleResult`, and exceptions `HubSpot401Error`, `HubSpotRateLimitError`, `HubSpotResponseError`, `HubSpotMissingResourceIdError`, `CrmStateStoreReadError`
- [x] T005 Create `src/crm_logger/state_store.py` with six functions per `contracts/crm-logger-contract.md`: `read_crm_store(path) -> CrmStateStore`, `get_pending_deals(store) -> list[dict]`, `get_new_deals(store) -> list[dict]`, `write_crm_outcome(path, gmail_message_id, outcome)`, `read_401_counter(path) -> int`, `write_401_counter(path, value)` — all using the merge-write pattern to preserve unknown top-level JSON keys
- [x] T006 [P] Create `src/crm_logger/client.py` with `HubSpotClient`: `__init__(token: str)`, `_call(method, path, body, *, msg_id=None, call_type=None) -> dict` (inserts `Authorization: Bearer <token>` header; raises `HubSpot401Error` on 401 without sleeping; raises `HubSpotRateLimitError` on 429; raises `HubSpotResponseError` on other non-2xx; calls `time.sleep(0.1)` after every non-401 response; increments `_call_count`), `call_count: int` property, `reset_call_count()`
- [x] T007 [P] Write unit tests for `src/crm_logger/state_store.py` in `tests/unit/test_crm_state_store.py`: `test_read_crm_store_missing_file_returns_empty`, `test_read_crm_store_returns_consecutive_401_cycles`, `test_read_crm_store_defaults_counter_to_0_when_absent`, `test_get_pending_deals_filters_correctly`, `test_get_new_deals_filters_correctly`, `test_write_crm_outcome_updates_outcome_field` — run `pytest tests/unit/test_crm_state_store.py` to confirm they FAIL before T005 is wired up
- [x] T008 [P] Implement `split_name(sender_name: str | None) -> tuple[str, str]` and `truncate_dealname(subject: str) -> str` helpers at the top of `src/crm_logger/log_deal.py` per `data-model.md` FR-014/FR-004 rules (these are pure functions, no dependencies)

**Checkpoint**: T004–T008 complete → user story phases may begin in parallel

---

## Phase 3: User Story 1 — Confirmed Deal Auto-Logged to HubSpot (Priority: P1) 🎯 MVP

**Goal**: A `DealPayload` read from the state store is written to HubSpot as a contact + linked deal in a single `sync_deals_to_crm` call. Already-logged deals are skipped (FR-002).

**Independent Test**: Seed one `deal_extracted` entry with 9 payload fields in a temp `processed_ids.json`. Call `run_crm_cycle(state_path, token)`. Verify HubSpot contains one contact matching `sender_email` and one deal matching `subject`. Verify state transitions to `crm-logged`.

### Tests for User Story 1

- [x] T009 [P] [US1] Write `test_search_contact_found_returns_id`, `test_search_contact_not_found_returns_none`, `test_search_contact_multi_match_selects_lowest_id`, `test_upsert_contact_finds_existing`, `test_upsert_contact_creates_new`, `test_create_deal_returns_id` in `tests/unit/test_hubspot_client.py` using `unittest.mock.patch` on `requests.Session.request` — verify FAIL before T011–T013
- [x] T010 [P] [US1] Write `test_log_deal_creates_contact_and_deal_returns_crm_logged` (mock client returns IDs; verify state written as `crm-logged`) and `test_log_deal_skips_deal_already_crm_logged` (FR-002; verify zero client calls) in `tests/unit/test_log_deal.py` — verify FAIL before T014

### Implementation for User Story 1

- [x] T011 [P] [US1] Implement `HubSpotClient.search_contact(email: str) -> str | None` in `src/crm_logger/client.py`: POST `/crm/v3/objects/contacts/search` with email filter; return lowest-ID contact ID from results or `None` if empty; log WARN on multi-match
- [x] T012 [P] [US1] Implement `HubSpotClient.upsert_contact(email: str, firstname: str, lastname: str) -> str` in `src/crm_logger/client.py`: call `search_contact()` first; if found return existing ID; otherwise POST `/crm/v3/objects/contacts` and return new ID; raise `HubSpotMissingResourceIdError` if response missing `id`
- [x] T013 [US1] Implement `HubSpotClient.create_deal(deal: HubSpotDeal, contact_id: str) -> str` in `src/crm_logger/client.py`: POST `/crm/v3/objects/deals` with all 6 property keys and embedded `associations` field (associationTypeId 3, deal-to-contact); return deal `id`; raise `HubSpotMissingResourceIdError` if missing (depends on T011, T012)
- [x] T014 [US1] Implement `log_deal(payload: DealPayload, client: HubSpotClient, state_path: str) -> Literal["crm-logged", "crm-pending", "skipped"]` in `src/crm_logger/log_deal.py`: FR-002 idempotency gate (read store → skip if already `crm-logged`); call `upsert_contact()` then `create_deal()`; call `write_crm_outcome(state_path, id, "crm-logged")` on success; log INFO with deal ID; propagate `HubSpot401Error` unhandled (depends on T005, T008, T011–T013)
- [x] T015 [US1] Implement `run_crm_cycle(state_path: str, token: str) -> CrmCycleResult` in `src/crm_logger/orchestrator.py`: read store via `read_crm_store()`; instantiate `HubSpotClient(token)`; iterate `get_new_deals()` and call `log_deal()` for each; accumulate counts; return `CrmCycleResult` (depends on T005, T006, T014)
- [x] T016 [US1] Implement `sync_deals_to_crm` MCP tool in `src/crm_logger/server.py`: read `HUBSPOT_PRIVATE_APP_TOKEN` and `STATE_STORE_PATH` from env; call `run_crm_cycle()`; return `CrmCycleResult` as dict; catch all unhandled exceptions at the tool boundary and return `status="error"` with `error_details` (depends on T015)
- [x] T017 [US1] Run `pytest tests/unit/test_hubspot_client.py tests/unit/test_log_deal.py tests/unit/test_crm_state_store.py -v` — verify T009, T010, T007 all pass

**Checkpoint**: US1 complete — `sync_deals_to_crm` writes a confirmed deal to HubSpot and marks it `crm-logged`

---

## Phase 4: User Story 2 — Failed Write Enters Failable Pending State (Priority: P1)

**Goal**: Any HubSpot write failure (network error, non-401 4xx, 5xx, missing resource ID, invalid sender email) results in `crm-pending` state with a WARN log. The `401` error is propagated for cycle-level handling (Phase 7). The tool never silently drops a deal.

**Independent Test**: Mock `HubSpotClient.upsert_contact()` to raise a `ConnectionError`. Call `log_deal()`. Verify return value is `"crm-pending"`, state store entry has `outcome="crm-pending"`, and a WARN log was emitted.

### Tests for User Story 2

- [x] T018 [P] [US2] Write `test_log_deal_connection_error_returns_crm_pending`, `test_log_deal_4xx_returns_crm_pending`, `test_log_deal_missing_resource_id_returns_crm_pending`, `test_log_deal_invalid_sender_email_returns_crm_pending` in `tests/unit/test_log_deal.py` — verify FAIL before T020
- [x] T019 [P] [US2] Write `test_log_deal_401_propagates_as_hubspot_401_error` (verify `HubSpot401Error` is NOT caught inside `log_deal`) in `tests/unit/test_log_deal.py`

### Implementation for User Story 2

- [x] T020 [US2] Add FR-007 error handling wrapper in `log_deal()` in `src/crm_logger/log_deal.py`: guard `sender_email` validation first (`→ crm-pending + WARN "invalid_sender_email"` if invalid); wrap HubSpot calls in `try/except (requests.RequestException, HubSpotRateLimitError, HubSpotResponseError, HubSpotMissingResourceIdError)`; on any catch call `write_crm_outcome(..., "crm-pending")` and log WARN with Gmail message ID and reason; do NOT catch `HubSpot401Error`
- [x] T021 [US2] Add FR-013 state-store write failure handling in `log_deal()` in `src/crm_logger/log_deal.py`: wrap the `write_crm_outcome(..., "crm-logged")` call in try/except OSError; on failure log ERROR with Gmail message ID and I/O reason; leave deal state as `crm-pending`
- [x] T022 [US2] Run `pytest tests/unit/test_log_deal.py -v` — verify T018 and T019 tests pass

**Checkpoint**: US1 + US2 complete — all write failures produce `crm-pending`; no silent drops

---

## Phase 5: User Story 3 — Rate-Limit-Safe Burst Processing (Priority: P2)

**Goal**: Sequential HubSpot API calls are spaced by ≥100ms. The `HubSpotClient._call()` enforces this unconditionally. N deals × 3 calls complete without triggering a 429. Each call is DEBUG-logged.

**Independent Test**: Instantiate `HubSpotClient` with a mock session. Call `_call()` 3 times. Measure elapsed time ≥ 200ms (3 calls × 100ms delay, with delay applied after each non-401 response).

### Tests for User Story 3

- [x] T023 [P] [US3] Write `test_call_sleeps_100ms_after_each_non_401_response` (mock `time.sleep`; verify called with 0.1 after each non-401 call) and `test_call_count_increments_per_call` (verify `client.call_count` equals number of `_call()` invocations) in `tests/unit/test_hubspot_client.py`

### Implementation for User Story 3

- [x] T024 [US3] Add FR-006 DEBUG log in `HubSpotClient._call()` in `src/crm_logger/client.py`: before sending the request, log `[DEBUG] HubSpot call #%d: %s %s (msg_id=%s)` using `self._call_count + 1`, method, path, and the `msg_id` parameter; pass `msg_id` and `call_type` through from `upsert_contact()`, `search_contact()`, and `create_deal()` callers
- [x] T025 [US3] Add FR-011 per-cycle call counter check in `run_crm_cycle()` in `src/crm_logger/orchestrator.py`: before processing each deal (both pending and new), check `client.call_count >= 90`; if so, log WARN with deferred count, write all remaining unprocessed deals to `crm-pending` via `write_crm_outcome()`, and break out of both loops
- [x] T026 [US3] Run `pytest tests/unit/test_hubspot_client.py -v` — verify T023 tests pass

**Checkpoint**: US3 complete — burst processing stays within 100 req/10s; circuit breaker defers at 90 calls/cycle

---

## Phase 6: User Story 4 — Pending Deals Drain Before New Deals (Priority: P2)

**Goal**: Each `run_crm_cycle()` call processes all `crm-pending` entries first, then `deal_extracted` entries. A steady stream of new deals cannot starve pending ones.

**Independent Test**: Seed two `crm-pending` entries and one `deal_extracted` entry in the state store. Call `run_crm_cycle()` with a mock `HubSpotClient` that records call order by Gmail message ID. Verify the two pending IDs appear in calls before the new deal ID.

### Tests for User Story 4

- [x] T027 [P] [US4] Write `test_run_crm_cycle_drains_pending_before_new_deals` in `tests/unit/test_orchestrator.py`: seed store with 2 `crm-pending` + 1 `deal_extracted`; mock `log_deal` to record call order; assert pending deals called first

### Implementation for User Story 4

- [x] T028 [US4] Update `run_crm_cycle()` in `src/crm_logger/orchestrator.py` to process `get_pending_deals()` before `get_new_deals()`: first loop over pending entries → call `log_deal()`; then loop over new entries → call `log_deal()` (FR-008 drain-first order)
- [x] T029 [US4] Run `pytest tests/unit/test_orchestrator.py -v` — verify T027 passes

**Checkpoint**: US4 complete — pending deals always drain first; no starvation possible

---

## Phase 7: User Story 5 — Per-Cycle Limits, Name Parsing, and Retry Payload Integrity (Priority: P2)

**Goal**: Three concrete invariants enforced independently: (1) per-cycle 90-call circuit breaker defers remaining deals to `crm-pending`; (2) `sender_name` is split deterministically into `firstname`/`lastname`; (3) all 9 DealPayload fields are persisted in `deal_extracted`/`crm-pending`/`crm-logged` entries so CRM logging on restart requires zero Gmail API calls. Also covers the cross-feature changes to `001-gmail-intake` that write those 9 fields.

**Independent Test**: Three separate unit tests per US5 acceptance scenario (spec.md §US5). See T030–T034.

### Tests for User Story 5

- [x] T030 [P] [US5] Write `test_circuit_breaker_31_deals_writes_30_defers_1` (seed 31 `deal_extracted` entries; mock client; verify exactly 90 `_call()` invocations and 1 entry written to `crm-pending` at cycle end) and `test_circuit_breaker_deferred_entry_has_crm_pending_outcome` in `tests/unit/test_orchestrator.py`
- [x] T031 [P] [US5] Write `test_split_name_three_tokens_splits_on_first_space` (`"Jane Doe Smith"` → `("Jane", "Doe Smith")`), `test_split_name_single_token` (`"Alice"` → `("Alice", "")`), `test_split_name_none_returns_empty_tuple`, `test_truncate_dealname_260_chars_truncates_to_255`, `test_truncate_dealname_255_chars_unchanged` in `tests/unit/test_log_deal.py`
- [x] T032 [P] [US5] Write `test_401_cycle_counter_increments_on_qualifying_cycle` (all-401 cycle: counter goes 0→1), `test_mixed_cycle_success_resets_counter` (at least one success → counter stays 0), `test_zero_call_cycle_counter_unchanged` (no HubSpot calls → counter unchanged), `test_suspension_fires_at_3_consecutive_401_cycles` (FATAL log emitted; tool returns `suspended=True`), `test_restart_resets_counter_to_0_with_warn_log` in `tests/unit/test_orchestrator.py`
- [x] T033 [P] [US5] Write `test_fr015_9_fields_in_crm_pending_entry_after_write_failure` (mock write failure; verify all 9 payload fields present in the `crm-pending` entry written to state store) and `test_fr015_orchestrator_reconstructs_dealpayload_from_state_store_no_gmail_call` (seed crm-pending entry with 9 fields; mock log_deal to assert payload is fully populated; verify zero Gmail calls) in `tests/unit/test_log_deal.py`
- [x] T034 [P] [US5] Write `test_append_message_with_extra_fields_persists_9_payload_fields` and `test_atomic_write_preserves_consecutive_401_cycles_from_existing_json` in `tests/unit/test_state_store.py` (001's existing test file)

### Implementation for User Story 5

- [x] T035 [US5] Add FR-007 within-cycle 401 abort in `run_crm_cycle()` in `src/crm_logger/orchestrator.py`: catch `HubSpot401Error` propagated from `log_deal()`; write all remaining unprocessed deals in current cycle to `crm-pending` without further HubSpot calls; then fall through to cross-cycle counter logic
- [x] T036 [US5] Add FR-007 cross-cycle 401 counter in `run_crm_cycle()` in `src/crm_logger/orchestrator.py`: after the deal loops complete, determine if the cycle was a qualifying 401 cycle (≥1 401 response AND 0 successful responses); if so increment and write `consecutive_401_cycles` via `write_401_counter()`; if successful responses occurred, reset counter to 0
- [x] T037 [US5] Add FR-007 suspension mode check at the start of `run_crm_cycle()` in `src/crm_logger/orchestrator.py`: read `consecutive_401_cycles` via `read_401_counter()`; if ≥ 3, log FATAL and return `CrmCycleResult(suspended=True, ...)`; if ≥ 3 AND this is startup (add an `is_startup: bool = False` parameter), log WARN and reset counter to 0 before proceeding
- [x] T038 [US5] Wire `split_name()` into `log_deal()` in `src/crm_logger/log_deal.py`: call `split_name(payload.sender_name)` to get `(firstname, lastname)` and pass to `client.upsert_contact()` (T008 already implemented `split_name`; this task connects it to the call site)
- [x] T039 [US5] Update `src/gmail_intake/state_store.py`: (a) update `_atomic_write()` to read existing JSON before writing and merge unknown top-level keys (preserve `consecutive_401_cycles`); (b) add `extra_fields: dict | None = None` parameter to `append_message()` and merge into the serialized message dict when provided
- [x] T040 [US5] Update `src/gmail_intake/server.py` to pass 9 DealPayload fields as `extra_fields` to `append_message()` for every `deal_extracted` entry (FR-015 implementation dependency)
- [x] T041 [US5] Extend `ProcessedMessageOutcome` Literal in `src/gmail_intake/models.py` to include `"crm-pending"` and `"crm-logged"` values; run `pytest tests/unit/ -v` — verify all T030–T034 tests pass and no regressions in 001 tests

**Checkpoint**: US5 complete — all 5 acceptance scenarios from spec.md §US5 verified by unit tests

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Integration test, full-suite verification, and OpenClaw wiring.

- [ ] T042 [P] Write integration test `tests/integration/test_sync_deals_to_crm.py`: seed one `deal_extracted` entry in a temp state store; call `run_crm_cycle()` against a real HubSpot sandbox account; assert `crm_logged == 1`; assert HubSpot contains the contact and deal; assert state store entry has `outcome="crm-logged"`
- [x] T043 [P] Run full unit suite `pytest tests/unit/ --tb=short -q` — confirm all tests green including 001-gmail-intake tests (no regressions from T039–T041 changes)
- [x] T044 Run quickstart.md Step 6 smoke test: `python -c "from crm_logger.orchestrator import run_crm_cycle; import os; r = run_crm_cycle(os.environ['STATE_STORE_PATH'], os.environ['HUBSPOT_PRIVATE_APP_TOKEN']); print(r)"` — confirm `CrmCycleResult(status='ok', ...)` with no exception
- [ ] T045 Verify OpenClaw MCP config includes the `crm-logger` server entry from `quickstart.md` Step 5; confirm `sync_deals_to_crm` tool is discoverable by OpenClaw
- [ ] T046 [P] Run `pytest tests/ --tb=short -q` (full suite: unit + integration) — confirm all green; record pass count in PHR

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1, T001–T003)**: No dependencies — start immediately
- **Foundational (Phase 2, T004–T008)**: Depends on Phase 1 — **BLOCKS all user story phases**
  - T004 (models) must complete first within Phase 2
  - T005, T006, T007, T008 can run in parallel once T004 is done
- **US1 (Phase 3, T009–T017)**: Depends on Phase 2 completion
- **US2 (Phase 4, T018–T022)**: Depends on Phase 3 (US2 adds error-path behaviour to `log_deal()` built in US1)
- **US3 (Phase 5, T023–T026)**: Depends on Phase 2 (can start in parallel with US1/US2 on separate branches)
- **US4 (Phase 6, T027–T029)**: Depends on Phase 3 (updates `run_crm_cycle()` from US1)
- **US5 (Phase 7, T030–T041)**: Depends on Phase 3 (circuit breaker builds on `run_crm_cycle()`) and Phase 4 (FR-007 401 handling builds on error handling from US2)
- **Polish (Phase 8, T042–T046)**: Depends on all user story phases complete

### User Story Dependencies (within each phase)

| Phase | Depends on |
|---|---|
| US1 (P3) | Foundational (P2) only |
| US2 (P4) | US1 — adds error paths to `log_deal()` |
| US3 (P5) | Foundational (P2) only — `_call()` and orchestrator circuit breaker are independent |
| US4 (P6) | US1 — updates `run_crm_cycle()` built in US1 |
| US5 (P7) | US1 + US2 — 401 counter builds on error handling; cross-feature changes are independent |

### Within Each Phase

- Test tasks (`T009`, `T010`, `T018`, etc.) should be written before the implementation tasks they test — run them to confirm FAIL, then implement, then confirm PASS
- Within US1: T011 and T012 are independent (different methods); T013 depends on T012; T014 depends on T008 + T011–T013; T015 depends on T014; T016 depends on T015

---

## Parallel Opportunities

### Phase 1
All 3 tasks (`T001`, `T002`, `T003`) can run in parallel.

### Phase 2 (after T004)
```
T004 (models) → T005, T006, T007, T008 all in parallel
```

### Phase 3 (US1)
```
# Tests and client methods in parallel:
T009 (client tests) || T010 (log_deal tests) || T011 (search_contact) || T012 (upsert_contact)
# Then sequentially:
T013 (create_deal) → T014 (log_deal) → T015 (orchestrator) → T016 (server) → T017 (verify)
```

### US3 and US4 can start simultaneously after Phase 2
```
US3: T023 (tests) || T024 (debug log) → T025 (circuit breaker) → T026 (verify)
US4: T027 (tests) → T028 (drain order) → T029 (verify)
```

### Phase 8
```
T042 (integration test) || T043 (unit suite) || T044 (smoke test) || T045 (MCP config) → T046 (full suite)
```

---

## Parallel Example: User Story 1

```bash
# Step 1 — parallel: write tests + begin client methods
Task: T009 — write HubSpotClient unit tests in tests/unit/test_hubspot_client.py
Task: T010 — write log_deal happy-path tests in tests/unit/test_log_deal.py
Task: T011 — implement search_contact() in src/crm_logger/client.py
Task: T012 — implement upsert_contact() in src/crm_logger/client.py

# Step 2 — sequential: wire up the full call chain
Task: T013 — implement create_deal() in src/crm_logger/client.py
Task: T014 — implement log_deal() in src/crm_logger/log_deal.py
Task: T015 — implement run_crm_cycle() in src/crm_logger/orchestrator.py
Task: T016 — implement sync_deals_to_crm in src/crm_logger/server.py
Task: T017 — run pytest to verify US1 tests pass
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 — happy-path CRM write
4. Complete Phase 4: US2 — error handling → `crm-pending`
5. **STOP and VALIDATE**: `sync_deals_to_crm` handles both success and failure paths
6. Deploy/demo — core value delivered (auto-logging + safe fallback)

### Incremental Delivery

1. Setup + Foundational → scaffold ready
2. US1 → confirmed deal auto-logged to HubSpot (MVP!)
3. US2 → failed writes produce `crm-pending` (safety net)
4. US3 → burst-safe under free-tier rate limits
5. US4 → drain ordering enforced (no pending starvation)
6. US5 → circuit breaker + name parsing + payload persistence + cross-feature 001 changes

Each story adds value without breaking the previous ones. The integration test (T042) can be run after any story phase to confirm end-to-end behaviour.

---

## Notes

- `[P]` tasks touch different files and have no blocking dependency — safe to run concurrently
- `[Story]` label traces every task back to a user story in `spec.md`
- Every test task should be run to confirm FAIL before the corresponding implementation task
- The cross-feature changes in US5 (T039–T041) touch `001-gmail-intake` — run the 001 unit tests after each change to guard against regressions
- Commit after each `Checkpoint` line to create clean rollback points
- `consecutive_401_cycles` resets to 0 on restart — simulate by seeding the value in the temp state store for T032 tests
