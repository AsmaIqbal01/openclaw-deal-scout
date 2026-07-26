# Tasks: Email Scheduling & Smart Send-Time Optimization (007)

**Input**: `specs/007-email-scheduling/` — spec.md, plan.md, data-model.md, contracts/, research.md, quickstart.md
**ADRs**: ADR-0008 (Gmail API send), ADR-0009 (in-process threading model)

---

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: parallelizable — different files, no dependency on incomplete tasks in the same batch
- **[Story]**: maps to spec.md user story (US1–US4)
- All file paths are relative to repo root

---

## Phase 1: Setup

**Purpose**: Create the `email_scheduler` package skeleton and register it with the project.

- [x] T001 Create `src/email_scheduler/` directory; add stub `src/email_scheduler/__init__.py` (empty exports, package docstring only); verify `src/email_scheduler` is on the Python path (check `pyproject.toml` package discovery — add `email_scheduler` to `packages` if required)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures and I/O layer required by every user story. Nothing in Phase 3–6 can begin until this phase is complete.

**⚠️ CRITICAL**: queue_store.py (T004) and audit_logger.py (T005) block all four user stories.

- [x] T002 [P] Implement `EmailSchedulerConfig` dataclass and `load_email_config()` in `src/email_scheduler/config.py` — read and validate `GMAIL_CREDENTIALS_PATH` (required), `EMAIL_FROM_ADDRESS` (required), `EMAIL_QUEUE_PATH` (optional; default `<STATE_STORE_PATH dir>/email_queue.json`), `EMAIL_AUDIT_LOG_PATH` (optional; default), `EMAIL_TEMPLATE_PATH` (optional), `EMAIL_ENABLED` (bool, default True); call `sys.exit(1)` on any required-var absence
- [x] T003 [P] Implement `ScheduledEmail` + `EmailEvent` dataclasses and `EmailStatus` + `EventType` enums in `src/email_scheduler/models.py` — all fields per data-model.md; include `dataclasses.asdict()` compatibility (no custom serialisers needed); both classes are pure data, no I/O
- [x] T004 Implement `EmailQueueStore` in `src/email_scheduler/queue_store.py` — in-memory list backed by atomic JSON file (`tempfile + os.replace`); file structure `{"version": 1, "emails": [...]}` per data-model.md; `threading.Lock` on all write operations; methods: `load(path)` (called once at startup), `list_emails(status_filter)`, `get_by_id(id)`, `create(email)` (deduplication check per FR-014 before insert); expose singleton via `get_store()` module-level function (depends on T002, T003)
- [x] T005 Implement `AuditLogger` in `src/email_scheduler/audit_logger.py` — wraps `logging.FileHandler` (append mode, `propagate=False`); one JSON line per `EmailEvent` via `logger.info(json.dumps(dataclasses.asdict(event)))`; expose singleton via `get_audit_logger()` (depends on T003)

**Checkpoint**: `EmailQueueStore` and `AuditLogger` exist and are independently testable in isolation before any user story work begins.

---

## Phase 3: User Story 1 — Auto-Schedule on Deal Detection (Priority: P1) 🎯 MVP

**Goal**: When a deal reaches `discord-notified` status in the pipeline, the scheduler creates a `"scheduled"` email entry in `email_queue.json` with rendered subject/body, writes a `scheduled` audit event, and returns to the orchestrator without raising.

**Independent Test**: Run `pytest tests/unit/test_email_scheduler_scheduler.py -k schedule_for_deal -v` — all schedule_for_deal paths pass. Then run a pipeline cycle with a `discord-notified` deal in the state store and verify `email_queue.json` gains a new `"scheduled"` entry and `email_audit.log` gains a `scheduled` event.

- [x] T006 [P] [US1] Implement `render_email(deal_payload, template_str) → (subject, body)` in `src/email_scheduler/template.py` — subject derivation rule per FR-009 (deal_summary → subject field → hardcoded fallback); body fallback rules (absent field = None / missing / whitespace-only after strip); load template from `EMAIL_TEMPLATE_PATH` env var if set; fall back to built-in default template on any read failure; use `str.format_map()` with `defaultdict(str)` to substitute placeholders silently
- [x] T007 [US1] Implement `schedule_for_deal(deal_payload: dict) → dict` in `src/email_scheduler/scheduler.py` — validate `gmail_message_id` present (else return `{"status":"error","reason":"missing_gmail_message_id"}`); validate `sender_email` (FR-008 rule — one `@`, non-empty local-part, domain with `.`); check state store for `discord-notified` status (read `STATE_STORE_PATH` to confirm deal is eligible); run dedup check via `get_store()` (active statuses: scheduled/approved/sent); create `ScheduledEmail` entry; call `get_audit_logger().write()` for `scheduled`/`no-recipient`/`duplicate-skipped`/`scheduler-error` events; wrap entire function body in `try/except Exception` — catch all, write `scheduler-error` audit event, return `{"status":"error","reason":"..."}` (MUST NOT raise); return `{"status":"scheduled"|"skipped"|"error","reason":str}` (depends on T004, T005, T006)
- [x] T008 [US1] Export `schedule_for_deal` from `src/email_scheduler/__init__.py`; initialise `EmailQueueStore` and `AuditLogger` singletons lazily from `load_email_config()` on first call; add `__all__ = ["schedule_for_deal", "dispatch_pending"]` (depends on T007)
- [x] T009 [US1] Add step 4a to `run_cycle()` in `src/pipeline_orchestrator/runner.py` — after `_update_notify_retry()`, iterate over `result1.get("deals_extracted", [])` and call `schedule_for_deal(deal_payload)` per deal; construct `deal_payload` dict mapping `message_id→gmail_message_id`, `summary→deal_summary` per plan.md Integration Points; log `[WARN] scheduler-error: {reason}` on error status; add `emails_scheduled` counter; wrap in belt-and-suspenders `try/except Exception` per FR-017 (depends on T008)
- [x] T010 [P] [US1] Write unit tests in `tests/unit/test_email_scheduler_config.py` — valid minimal config, missing `GMAIL_CREDENTIALS_PATH` → SystemExit, missing `EMAIL_FROM_ADDRESS` → SystemExit, invalid `EMAIL_ENABLED` string → SystemExit, defaults applied for optional vars, `EMAIL_QUEUE_PATH` override respected; minimum 8 test cases
- [x] T011 [P] [US1] Write unit tests in `tests/unit/test_email_scheduler_template.py` — subject rule all 3 branches (deal_summary present, deal_summary absent+subject present, both absent); body fallback for missing sender_name → "Hi there,"; missing company_name → line omitted; missing deal_summary → subject substituted; whitespace-only field treated as absent; custom template loaded from file; template file unreadable → built-in used; minimum 10 test cases
- [x] T012 [P] [US1] Write unit tests in `tests/unit/test_email_scheduler_queue_store.py` — store initialised empty; `create()` adds entry; `list_emails()` filters by status; `get_by_id()` returns entry or None; dedup blocks create for active statuses (scheduled/approved/sent); dedup allows create when existing entry is cancelled or failed; atomic write creates file (tmp+rename); threading.Lock acquired on write; minimum 10 test cases
- [x] T013 [US1] Write unit tests in `tests/unit/test_email_scheduler_scheduler.py` (schedule_for_deal section) — valid deal → `status:"scheduled"`; missing `gmail_message_id` → `status:"error"`; invalid `sender_email` → `status:"skipped","reason":"no_recipient"`; duplicate active entry → `status:"skipped","reason":"duplicate"`; deal not at `discord-notified` → `status:"skipped","reason":"not_discord_notified"`; audit events written for each path; exception inside schedule → caught, `scheduler-error` event written, returns `status:"error"` (never raises); minimum 8 test cases (depends on T009)

**Checkpoint**: `pytest tests/unit/test_email_scheduler_config.py tests/unit/test_email_scheduler_template.py tests/unit/test_email_scheduler_queue_store.py tests/unit/test_email_scheduler_scheduler.py -v` all pass. US1 is fully functional: pipeline cycle auto-schedules emails for new deals.

---

## Phase 4: User Story 2 — Operator Review & Approval Gate (Priority: P2)

**Goal**: Operator opens the dashboard, sees all scheduled/approved emails, clicks Approve or Cancel, and the status updates in `email_queue.json` with a `200` response and an audit event. All actions are idempotent.

**Independent Test**: With `status:"scheduled"` entries in the queue, `POST /api/emails/{id}/approve` returns `200 {"id":...,"status":"approved","approved_at":"..."}`. The queue file reflects the change. `GET /api/emails?status=approved` returns the entry. Repeat the approve request → same `200` with unchanged `approved_at` (idempotency confirmed).

- [x] T014 [P] [US2] Add `approve(email_id) → ScheduledEmail` and `cancel(email_id) → ScheduledEmail` methods to `EmailQueueStore` in `src/email_scheduler/queue_store.py` — approve: raises `KeyError` if not found, raises `ValueError(current_status)` if terminal (sent/cancelled/failed); sets `status:"approved"`, `approved_at:utcnow_iso()`; writes audit `approved` event via `get_audit_logger()`; idempotent (already-approved → return current without re-writing); cancel: only `sent` is a hard error (409); `failed→cancelled` permitted; idempotent on already-cancelled; writes `cancelled` audit event; all mutations acquire `threading.Lock`; all writes via `tempfile+os.replace` atomic pattern
- [x] T015 [P] [US2] Implement REST handlers `api_approve_email`, `api_cancel_email`, `api_list_emails` in `src/openclaw_gateway/routes/email_api.py` (new file, mirrors `routes/api.py` pattern) — each handler is `async def handler(request: Request) → JSONResponse`; extract `email_id` from `request.path_params["email_id"]`; use `await asyncio.to_thread(store.approve, email_id)` for writes (ADR-0009 pattern); map `KeyError → 404`, `ValueError → 409` with `current_status` in body, `OSError → 500`; `api_list_emails`: parse `status` query param (400 on invalid), `limit` (clamp 1–200), `offset`; return `{"emails":[...],"total":filtered_count,"offset":N}`; responses include `Access-Control-Allow-Origin: *` header
- [x] T016 [US2] Register 3 new routes in `src/openclaw_gateway/server.py` — import `api_approve_email`, `api_cancel_email`, `api_list_emails` from `openclaw_gateway.routes.email_api`; add `mcp.custom_route("/api/emails", methods=["GET"])(api_list_emails)`, `mcp.custom_route("/api/emails/{email_id}/approve", methods=["POST"])(api_approve_email)`, `mcp.custom_route("/api/emails/{email_id}/cancel", methods=["POST"])(api_cancel_email)` (depends on T015)
- [x] T017 [US2] Add email queue panel to `src/openclaw_gateway/static/dashboard.html` — new panel section (consistent with existing "Deals" and "Pipeline Cycles" panel style); table columns: Recipient, Subject (truncated to 60 chars), Status badge, Proposed Send, Created; Approve and Cancel buttons on each `"scheduled"` row; buttons POST to `/api/emails/{id}/approve` and `/api/emails/{id}/cancel` then refresh panel; panel auto-refreshes with the 60 s global refresh; empty state: "No pending emails" (depends on T016)
- [x] T018 [P] [US2] Extend `tests/unit/test_email_scheduler_queue_store.py` with approve/cancel tests — `approve()` changes status; `approved_at` set; idempotent (second approve returns same timestamp); `approve()` on `sent` raises `ValueError`; `approve()` on `cancelled` raises `ValueError`; `approve()` on `failed` raises `ValueError`; `cancel()` on `scheduled` succeeds; `cancel()` on `failed` succeeds; `cancel()` on `sent` raises `ValueError`; cancel idempotent; minimum 10 new test cases
- [x] T019 [US2] Write unit tests in `tests/unit/test_email_scheduler_api.py` — mock `EmailQueueStore`; `POST /approve` on scheduled → 200 with approved status; `POST /approve` on already-approved → 200 idempotent; `POST /approve` on sent → 409; `POST /approve` on unknown id → 404; `POST /cancel` on scheduled → 200; `POST /cancel` on sent → 409; `POST /cancel` on unknown id → 404; `GET /api/emails` default → 200 with emails list; `GET /api/emails?status=scheduled` → filtered; `GET /api/emails?status=invalid` → 400; `GET /api/emails?limit=300` → clamped to 200; minimum 12 test cases (depends on T016)

**Checkpoint**: `pytest tests/unit/test_email_scheduler_queue_store.py tests/unit/test_email_scheduler_api.py -v` all pass. Dashboard shows scheduled emails; approve/cancel work end-to-end.

---

## Phase 5: User Story 3 — Smart Send-Time (UK Business Hours) (Priority: P3)

**Goal**: Approved emails dispatch only within Mon–Fri 09:00–17:00 Europe/London (DST-aware). Failed sends retry up to 3 times with exponential back-off (60 s / 120 s / 240 s). After 3 failures, email is marked `"failed"` with a warning in `pipeline.log`.

**Independent Test**: Approve an email. Mock the time to Saturday 14:00 Europe/London and run `dispatch_pending()` — verify `dispatched:0`, `skipped:1`. Mock time to Monday 09:05 Europe/London — verify `dispatched:1`. Mock Gmail API to raise `HttpError 500` three times — verify email reaches `status:"failed"` with `retry_count:3` and `retry_after:null`.

- [x] T020 [P] [US3] Implement `build_send_service(credentials_path: str)` in `src/email_scheduler/auth.py` — loads `token.json` (co-located with `credentials_path`); `SEND_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]`; refresh token if expired using `creds.refresh(google.auth.transport.requests.Request())`; build Gmail API service via `googleapiclient.discovery.build('gmail', 'v1', credentials=creds)`; raise `AuthError` (from `gmail_intake.models`) on any credential or refresh failure; mirrors `gmail_intake.gmail_client.build_service()` pattern per ADR-0008
- [x] T021 [P] [US3] Implement `is_business_hours(dt_utc: datetime) → bool` and `next_business_window(dt_utc: datetime) → datetime` in `src/email_scheduler/scheduler.py` — use `from zoneinfo import ZoneInfo; ZoneInfo("Europe/London")`; business hours: weekday < 5 (Mon=0 … Fri=4) and 9 ≤ hour < 17; `next_business_window`: if already open return dt_utc unchanged; if same-day before 09:00 return same day 09:00 UTC-equivalent; if after 17:00 or weekend advance to next weekday 09:00; handle DST via ZoneInfo; `ZoneInfoNotFoundError` → log `[WARN] zoneinfo_unavailable`, fall back to UTC
- [x] T022 [US3] Implement `dispatch_pending() → dict` in `src/email_scheduler/scheduler.py` — iterates `get_store().list_emails(status_filter="approved")`; for each entry: skip if not `is_business_hours(now_utc)` or `retry_after` not elapsed (count as `skipped`); call `build_send_service()` and `service.users().messages().send()`; on success: update `status:"sent"`, `sent_at:utcnow_iso()`, write `sent` audit event; on failure: increment `retry_count`; set `retry_after` = `failed_at + [60, 120, 240][retry_count-1]`; if `retry_count == 3`: set `status:"failed"`, `retry_after:null`, write `failed` audit event with `retry_count:3`, append `[WARN]` to `pipeline.log`; `status` stays `"approved"` until all 3 retries exhausted; wrap entire function body in `try/except` — MUST NOT raise; return `{"dispatched":N,"skipped":N,"failed":N}` (depends on T020, T021, T004)
- [x] T023 [US3] Export `dispatch_pending` from `src/email_scheduler/__init__.py` (depends on T022)
- [x] T024 [US3] Add step 4b to `run_cycle()` in `src/pipeline_orchestrator/runner.py` — after all step-4a calls complete, call `dispatch_pending()` unconditionally (even when `step1_abort` was True — previously approved emails need dispatch); log `emails_dispatched`, `emails_skipped`, `emails_failed` counts; wrap in belt-and-suspenders `try/except Exception` per FR-017 (depends on T023)
- [x] T025 [P] [US3] Extend `tests/unit/test_email_scheduler_scheduler.py` with dispatch/business-hours tests — `is_business_hours()` returns True inside window; False on Saturday; False at 17:00 exactly; True at 09:00; DST: 08:15 UTC in BST (April) = 09:15 BST → True; `next_business_window()` advances past weekend; advances past 17:00; returns same time if already open; `dispatch_pending()` with mocked Gmail API success → `dispatched:1`; `dispatch_pending()` with HttpError 500 three times → `retry_count:3`, `status:"failed"`, pipeline.log warning; retry_after respected (skipped when not elapsed); minimum 15 test cases
- [x] T026 [US3] Write integration tests in `tests/integration/test_email_scheduling_e2e.py` — mock Gmail API + real `EmailQueueStore` (temp dir); full cycle: `schedule_for_deal()` → approve via store → `dispatch_pending()` dispatches → `status:"sent"`; retry flow: mock 3 consecutive failures → `status:"failed"`; outside business hours: mock time to weekend → `dispatch_pending()` → `skipped:1`; startup recovery: write `sent` audit event manually, restart store, call `_repair_from_audit()` → entry corrected + `recovered` event written; minimum 8 test cases (depends on T024)

**Checkpoint**: `pytest tests/unit/test_email_scheduler_scheduler.py tests/integration/test_email_scheduling_e2e.py -v` all pass. Emails dispatch during business hours; retries and failures work correctly.

---

## Phase 6: User Story 4 — Full Audit Trail (Priority: P4)

**Goal**: Every email lifecycle event (scheduled, approved, sent, cancelled, failed, no-recipient) appears in `email_audit.log` within 5 seconds. Dashboard exposes the full event history. Startup recovery repairs any queue ↔ audit mismatch from a previous crash.

**Independent Test**: Walk a single email through scheduled → approved → sent. `GET /api/email-events` returns three events in reverse-chronological order with correct `actor` values. Cancel a second email and verify two events (scheduled, cancelled). Restart the store after injecting a mismatch and verify `recovered` event appears.

- [x] T027 [P] [US4] Add `_repair_from_audit(audit_log_path: Path)` and startup-recovery logic to `src/email_scheduler/queue_store.py` — scan `email_audit.log` for `sent` events; for each: if matching queue entry has `status:"approved"`, set to `status:"sent"`, `sent_at` from event timestamp; write `recovered` audit event; handle corrupted `email_queue.json` on startup (log warning, init empty queue, write fresh file); handle corrupted `email_audit.log` on startup (log warning, start fresh, write `recovery-warning` event); call `_repair_from_audit()` inside `load()` after reading the queue file
- [x] T028 [P] [US4] Add `api_list_email_events` handler to `src/openclaw_gateway/routes/email_api.py` — reads all events from `AuditLogger` cache (in-memory list updated on each `write()` call); parse `limit` (clamp 1–500) and `offset` query params; sort by `timestamp` descending; return `{"events":[...],"total":all_events_count,"offset":N}` where `total` is the unfiltered count; `500` on audit log unreadable; no `event_type` filter param (unfiltered — as per contracts/email-scheduler-api.md)
- [x] T029 [US4] Register `GET /api/email-events` route in `src/openclaw_gateway/server.py` — import `api_list_email_events` from `openclaw_gateway.routes.email_api`; add `mcp.custom_route("/api/email-events", methods=["GET"])(api_list_email_events)` (depends on T028)
- [x] T030 [US4] Add audit history panel to `src/openclaw_gateway/static/dashboard.html` — new collapsible panel below email queue panel; table columns: Time, Event Type, Recipient, Actor, Error; newest-first order; `limit=50&offset=0` default; "Load more" button to paginate; empty state: "No audit events yet"; consistent panel style with existing dashboard (depends on T029)
- [x] T031 [P] [US4] Write unit tests in `tests/unit/test_email_scheduler_audit.py` — `AuditLogger.write()` appends one JSON line per event; all `EmailEvent` fields serialised; file created if absent; thread-safe (two threads write concurrently, both lines parse successfully); startup recovery: corrupted audit log → fresh file + `recovery-warning` event; startup recovery: `sent` audit event + `approved` queue entry → entry repaired + `recovered` event; `api_list_email_events` returns events newest-first; pagination via limit/offset; `total` is unfiltered count; minimum 12 test cases

**Checkpoint**: `pytest tests/unit/test_email_scheduler_audit.py -v` all pass. Dashboard history panel shows all lifecycle events. Startup recovery works correctly.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Backward-compatible extensions and regression verification.

- [x] T032 Extend `emit_cycle_summary()` in `src/pipeline_orchestrator/cycle_logger.py` to include optional email fields — add `emails_scheduled=0`, `emails_dispatched=0`, `emails_skipped=0`, `emails_failed=0` keyword args (all default 0); include them in the JSON log line only when at least one is non-zero (preserves backward compatibility with existing log parsers that expect the current 6-field format)
- [x] T033 Run full test suite to confirm zero regressions: `pytest tests/ -q` — target: all pre-existing 321 tests pass plus all new email_scheduler tests pass; fix any import errors or name collisions if found
- [ ] T034 Manual quickstart.md validation — execute scenarios 1–6 from `specs/007-email-scheduling/quickstart.md` against a live gateway with real `GMAIL_CREDENTIALS_PATH` and `EMAIL_FROM_ADDRESS`; verify each scenario passes; note any deviations; mark T034 complete when scenarios 1–5 pass (scenario 6 requires real Gmail send — mark separately if token not yet upgraded)

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
  └── Phase 2 (Foundational) — BLOCKS all phases below
        ├── Phase 3 (US1) — MVP: schedule_for_deal() + step 4a
        │     └── Phase 4 (US2) — approve/cancel REST + dashboard panel
        │           └── Phase 5 (US3) — dispatch_pending() + business hours + step 4b
        │                 └── Phase 6 (US4) — startup recovery + audit history panel
        │                       └── Phase 7 (Polish)
        └── (Phases 3–6 can proceed sequentially in priority order)
```

US3 (Phase 5) requires Phase 4 (US2) to be complete because `dispatch_pending()` reads approved entries that US2's approve endpoint creates. The phases are sequential P1 → P2 → P3 → P4.

### Within-Phase Parallel Opportunities

| Phase | Parallel batch | Tasks |
|---|---|---|
| Phase 2 | Batch A | T002, T003 (config + models — both pure data, no dependencies) |
| Phase 3 | Batch A | T006, T010, T011 (template.py + its tests; both pure, no queue dependency) |
| Phase 3 | Batch B | T012 (queue_store tests — after T004 done in Phase 2) |
| Phase 4 | Batch A | T014, T015, T018 (approve/cancel methods + REST handlers + their tests) |
| Phase 5 | Batch A | T020, T021, T025 (auth.py + business-hours functions + their tests) |
| Phase 6 | Batch A | T027, T028, T031 (startup recovery + api_list_email_events + audit tests) |

---

## Parallel Execution Examples

### Phase 2 — Foundational

```
Launch in parallel:
  Task T002: config.py (no dependencies)
  Task T003: models.py (no dependencies)
Then sequentially:
  Task T004: queue_store.py (needs T002, T003)
  Task T005: audit_logger.py (needs T003)
```

### Phase 3 — US1

```
Launch in parallel (after Phase 2 complete):
  Task T006: template.py
  Task T010: test_email_scheduler_config.py
  Task T011: test_email_scheduler_template.py
  Task T012: test_email_scheduler_queue_store.py (schedule paths)
Then sequentially:
  Task T007: schedule_for_deal() in scheduler.py
  Task T008: __init__.py exports
  Task T009: runner.py step 4a
  Task T013: scheduler tests (schedule_for_deal paths)
```

### Phase 5 — US3

```
Launch in parallel (after Phase 4 complete):
  Task T020: auth.py (build_send_service)
  Task T021: is_business_hours() + next_business_window() in scheduler.py
Then sequentially:
  Task T022: dispatch_pending() in scheduler.py (needs T020, T021)
  Task T023: __init__.py exports
  Task T024: runner.py step 4b
Launch in parallel:
  Task T025: scheduler tests (business-hours + dispatch paths)
  Task T026: integration tests (depends T024)
```

---

## Implementation Strategy

### MVP (Phase 1 + 2 + 3 only — US1 complete)

1. T001: package skeleton
2. T002 + T003 in parallel: config + models
3. T004 → T005: queue_store → audit_logger
4. T006 + T010 + T011 + T012 in parallel: template + unit tests
5. T007 → T008 → T009: schedule_for_deal chain
6. T013: scheduler unit tests
7. **STOP and VALIDATE**: `pytest tests/unit/test_email_scheduler_*.py -v`; run pipeline cycle with test deal; verify `email_queue.json` and `email_audit.log` populated

MVP deliverable: automatic email scheduling works end-to-end. No emails sent yet (operator approval and dispatch come in US2/US3).

### Incremental Delivery

- After US1 (MVP): scheduling works, queue visible in `email_queue.json`
- After US2: operator can approve/cancel via dashboard and REST; emails stay in `"approved"` state
- After US3: approved emails dispatch during business hours via Gmail API; full retry logic
- After US4: audit history panel in dashboard; startup recovery hardens the feature

---

## Notes

- [P] tasks = different files, safe to parallelise within the same phase
- `queue_store.py` grows across three phases (T004 → T014 → T027): T004 creates the file; T014 adds approve/cancel; T027 adds startup recovery — each addition is backward-compatible
- `scheduler.py` grows across two phases (T007 → T021/T022): T007 creates the file with `schedule_for_deal()`; T021/T022 add business-hours functions and `dispatch_pending()` — additions only, no rewrites
- `test_email_scheduler_scheduler.py` grows across two phases (T013 → T025): T013 covers `schedule_for_deal` paths; T025 covers business-hours + dispatch paths
- `test_email_scheduler_queue_store.py` grows across two phases (T012 → T018): T012 covers create/list/dedup; T018 covers approve/cancel
- All SMTP-equivalent sends use Gmail API `users().messages().send()` — see ADR-0008
- All queue writes use `threading.Lock` + `asyncio.to_thread()` in HTTP handlers — see ADR-0009
- T034 requires real `token.json` with `gmail.send` scope; skip Gmail send sub-test if one-time re-auth not yet done
