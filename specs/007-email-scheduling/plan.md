# Implementation Plan: Email Scheduling & Smart Send-Time Optimization

**Branch**: `007-email-scheduling` | **Date**: 2026-07-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/007-email-scheduling/spec.md`

---

## Summary

Add a new `email_scheduler` package that auto-schedules follow-up emails when deals
reach `discord-notified` status, enforces operator approval before any SMTP send,
dispatches only within Mon–Fri 09:00–17:00 Europe/London (DST-aware), and maintains
a full audit trail. The scheduler integrates as step 4 of the existing pipeline cycle
(004-pipeline-orchestrator) and exposes four new REST endpoints in the existing gateway
(005/006). No new processes or infrastructure are required.

---

## Technical Context

**Language/Version**: Python 3.12 (matches existing venv)
**Primary Dependencies**:
- `google-auth` + `google-api-python-client` (already in deps via gmail_intake) — Gmail API `users().messages().send()`
- `zoneinfo` (Python 3.9+ stdlib) — DST-aware Europe/London timezone evaluation
- `smtplib` + `email.mime` (Python stdlib) — fallback; not used (Gmail API preferred)
- `uuid` (Python stdlib) — UUID generation for email IDs
- `threading.Lock` (Python stdlib) — queue write serialization
- `asyncio` (Python stdlib) — `asyncio.to_thread()` for HTTP handler queue writes
- `logging.FileHandler` (Python stdlib) — thread-safe JSONL audit log
- FastMCP/Starlette (already in deps via openclaw_gateway) — four new REST endpoints
- No new third-party dependencies required

**Storage**:
- `email_queue.json` — atomic JSON file (temp+rename); in-memory dict as primary state
- `email_audit.log` — append-only JSONL via Python `logging.FileHandler`
- Both files reside in same directory as `processed_ids.json` (default)
- Override paths: `EMAIL_QUEUE_PATH`, `EMAIL_AUDIT_LOG_PATH` env vars

**Testing**: `pytest` (same as existing suite); `pytest-asyncio` for async handler tests
**Target Platform**: Ubuntu 22.04, systemd, WSL2, single-operator
**Performance Goals**: Dispatch latency ≤15 min after window opens; audit events within 5 s
**Constraints**: Gmail 500/day send cap; no external services; threading.Lock on all queue writes
**Scale/Scope**: Low-volume B2B — single operator, expected <20 emails/day

---

## Constitution Check

| Gate | Question | Answer | Status |
|---|---|---|---|
| 1 | Does this change introduce any paid dependency? | No — Gmail API send uses existing OAuth credentials and free quota | ✅ PASS |
| 2 | Does this change add a non-Gmail intake source? | No — Gmail is used for outbound send, not as a new intake source | ✅ PASS |
| 3 | Does this change require a runtime browser login? | No — OAuth scope upgrade is one-time setup; runtime is fully headless after token refresh | ✅ PASS |
| 4 | Does this change risk duplicate CRM entries or duplicate alerts? | No — FR-014 deduplicates by `gmail_message_id` across all active statuses | ✅ PASS |
| 5 | Does this change modify core pipeline files to add a notification target? | No — email_scheduler is a new independent package; runner.py gains step 4 (not a notification adapter change) | ✅ PASS |
| 6 | Does this change allow an exception to crash the agent process? | No — FR-017 + SC-008 guarantee no exception escapes `schedule_for_deal()`, `dispatch_pending()`, or gateway handlers | ✅ PASS |

**All 6 gates PASS. No Complexity Tracking violations.**

---

## Key Architectural Decisions

### Decision 1 — Gmail API send, not raw SMTP

**Chosen**: Gmail REST API `users().messages().send()` (scope: `https://www.googleapis.com/auth/gmail.send`).

**Rationale**: Reuses `google-api-python-client` already in deps; handles OAuth2 refresh
natively via the same credential pattern as `gmail_intake.gmail_client.build_service()`;
avoids manual XOAUTH2 base64 string construction required for raw `smtplib` SMTP.

**Scope note**: The one-time re-auth adds `gmail.send` scope alongside the existing
`gmail.readonly` scope in `token.json`. Both scopes can coexist in one token file.
`email_scheduler.auth` loads the token with `["https://www.googleapis.com/auth/gmail.send"]`
— if the token lacks this scope, the API returns 403 and the dispatch fails with a
`scheduler-error` audit event until the operator completes the one-time scope setup.

**Alternative rejected**: Raw `smtplib` SMTP over port 587 with XOAUTH2 — requires
manual base64 encoding of the XOAUTH2 auth string; no native token-refresh support.

### Decision 2 — zoneinfo for DST-aware scheduling

**Chosen**: `from zoneinfo import ZoneInfo; ZoneInfo("Europe/London")` (Python 3.9+ stdlib).

**Rationale**: Zero new dependencies; handles BST/GMT transitions via system tzdata
(available on Ubuntu 22.04 by default). `datetime.now(tz=ZoneInfo("Europe/London"))`
returns DST-correct local time.

**Fallback**: If `zoneinfo` raises `ZoneInfoNotFoundError` (tzdata not installed), the
scheduler falls back to UTC+0 (safe — more emails deferred rather than sent outside hours)
and logs `[WARN] zoneinfo_unavailable: falling back to UTC for window evaluation`.

**Alternative rejected**: `pytz` — external dependency, adds weight for no benefit given
Python 3.12 is the target runtime.

### Decision 3 — email_scheduler owns credential loading; 001-gmail-intake unchanged

**Chosen**: `email_scheduler.auth.build_send_service(credentials_path)` — a self-contained
module that replicates the credential-load + refresh pattern from
`gmail_intake.gmail_client.build_service()` but uses the `gmail.send` scope.

**Rationale**: Spec explicitly preserves "001 unchanged" as a constraint. Duplicating
~20 lines of credential-loading code is cheaper than a shared-module refactor. The two
functions differ only in `SCOPES` constant and service endpoint.

**Risk**: Credential-loading logic diverges over time. Accepted in v1; if 001 is extended
(e.g., write scope), a future spec can propose extracting a shared `gmail_intake.auth` module.

### Decision 4 — In-memory queue with lazy load; threading.Lock for all writes

**Chosen**: `EmailQueueStore` singleton — loads `email_queue.json` once at startup, keeps
the entire queue in memory, writes atomically to disk (temp+rename) on every mutation.
All write paths (HTTP handlers + scheduler thread) acquire a `threading.Lock`.

HTTP handlers (async coroutines) use `await asyncio.to_thread(_write_locked, ...)` to
offload lock acquisition to the thread pool, preventing event-loop starvation.

**Rationale**: Consistent with existing `pipeline_orchestrator` state-store pattern; avoids
re-reading the file on every API call; atomic writes prevent partial-write corruption.

**Capacity**: Queue is bounded only by disk. At <20 emails/day the file stays small (<1 MB
for years of operation). No eviction policy in v1.

### Decision 5 — Step 4 split: 4a per-deal scheduling, 4b single dispatch call

**Chosen**: After step 3 completes (regardless of per-deal errors), `run_cycle()` calls:
- Step 4a: `schedule_for_deal(deal_payload)` once per deal in `result1["deals_extracted"]`
  (scheduler checks `discord-notified` status internally via the state store; deduplication
  handles re-processing of already-scheduled deals)
- Step 4b: `dispatch_pending()` once per cycle (always, including cycles with zero new deals)

**Rationale**: `dispatch_pending()` must run every cycle to service emails that became
eligible since the last cycle (e.g., business window opened, retry_after elapsed). Calling
it unconditionally is simpler and correct.

**Step 1 abort propagation**: If `step1_abort` is `True`, step 4 is also skipped (no
`deals_extracted` to process and no new approvals are expected from a failed cycle).
`dispatch_pending()` is still called even when step1_abort is True — it drains any
previously approved emails that are now window-eligible.

### Decision 6 — email_audit.log via Python logging.FileHandler

**Chosen**: `AuditLogger` wraps a `logging.Logger` with a `FileHandler` (propagate=False,
same pattern as `CycleLogger` in pipeline_orchestrator). Each event is a single
`logger.info(json.dumps(event_dict))` call. Python's logging is thread-safe by default.

**Rationale**: Thread-safe without extra locking; consistent with `pipeline.log` pattern;
survives concurrent writes from HTTP handlers and the scheduler thread.

**Rotation**: Not applied in v1 (audit log should never be rotated — it's an immutable
record). `FileHandler` is append-only. If disk space becomes a concern, a future spec
can add `RotatingFileHandler` with an archival policy.

---

## Project Structure

### Documentation (this feature)

```
specs/007-email-scheduling/
├── plan.md              ← this file
├── research.md          ← Phase 0 research findings
├── data-model.md        ← ScheduledEmail + EmailEvent entities, state machine
├── quickstart.md        ← US1–US4 test scenarios
├── contracts/
│   └── email-scheduler-api.md   ← REST endpoint contracts (4 endpoints)
└── tasks.md             ← /sp.tasks output (not created by /sp.plan)
```

### Source Code

```
src/
├── email_scheduler/           ← NEW PACKAGE (007)
│   ├── __init__.py            ← Public API: schedule_for_deal(), dispatch_pending()
│   ├── config.py              ← EmailSchedulerConfig dataclass + load_email_config()
│   ├── models.py              ← ScheduledEmail + EmailEvent dataclasses; status enums
│   ├── queue_store.py         ← EmailQueueStore: in-memory + atomic JSON persistence
│   ├── audit_logger.py        ← AuditLogger: JSONL append to email_audit.log
│   ├── template.py            ← render_email(deal_payload) → (subject, body)
│   ├── auth.py                ← build_send_service(credentials_path) → Gmail API client
│   └── scheduler.py           ← is_business_hours(), next_window(), schedule_for_deal(),
│                                 dispatch_pending()
│
├── pipeline_orchestrator/
│   └── runner.py              ← MODIFIED: add step 4a + 4b (import email_scheduler)
│
└── openclaw_gateway/
    ├── server.py              ← MODIFIED: register 4 new mcp.custom_route()s
    └── routes/
        └── api.py             ← MODIFIED: add api_approve_email, api_cancel_email,
                                  api_list_emails, api_list_email_events handlers
        (dashboard.html will need 2 new panels — planned as a separate UI task)
```

### Tests

```
tests/
├── unit/
│   ├── test_email_scheduler_config.py      ← env var validation, defaults, paths
│   ├── test_email_scheduler_template.py    ← subject/body rendering + all fallbacks
│   ├── test_email_scheduler_queue_store.py ← CRUD, deduplication, atomic write, lock
│   ├── test_email_scheduler_audit.py       ← event write, startup recovery, fail paths
│   ├── test_email_scheduler_scheduler.py   ← business-hours gate, retry logic, DST
│   └── test_email_scheduler_api.py         ← REST handlers (approve/cancel/list)
└── integration/
    └── test_email_scheduling_e2e.py        ← schedule→approve→dispatch full flow
```

### Environment Variables (new for 007)

| Variable | Default | Required | Notes |
|---|---|---|---|
| `GMAIL_CREDENTIALS_PATH` | — | YES | Path to `credentials.json`; `token.json` co-located |
| `EMAIL_FROM_ADDRESS` | — | YES | Sender Gmail address (e.g., `you@gmail.com`) |
| `EMAIL_QUEUE_PATH` | `<STATE_STORE_PATH dir>/email_queue.json` | NO | Override queue file location |
| `EMAIL_AUDIT_LOG_PATH` | `<STATE_STORE_PATH dir>/email_audit.log` | NO | Override audit log location |
| `EMAIL_TEMPLATE_PATH` | (built-in default template) | NO | Path to plain-text body template |
| `EMAIL_ENABLED` | `true` | NO | Set to `false` to skip dispatch without removing the scheduler from the cycle |

`GMAIL_CREDENTIALS_PATH` may already be set for 001-gmail-intake; email_scheduler reuses it.

---

## Integration Points

### 004 → 007 (runner.py step 4)

In `run_cycle()`, after `_update_notify_retry()` completes, add:

```python
# ── Step 4a: Schedule emails for newly processed deals ────────────────
emails_scheduled = 0
for deal in result1.get("deals_extracted", []):
    deal_payload = {
        "gmail_message_id": deal.get("message_id"),
        "sender_email": deal.get("sender_email"),
        "sender_name": deal.get("sender_name"),
        "subject": deal.get("subject"),
        "company_name": deal.get("company_name"),
        "deal_summary": deal.get("summary"),
    }
    try:
        from email_scheduler import schedule_for_deal
        r = schedule_for_deal(deal_payload)
        if r.get("status") == "scheduled":
            emails_scheduled += 1
        elif r.get("status") == "error":
            logger.warning("step 4a scheduler-error: %s", r.get("reason"))
    except Exception:
        logger.exception("step 4a: unhandled exception — scheduler did not honour no-raise contract")

# ── Step 4b: Dispatch approved emails ─────────────────────────────────
try:
    from email_scheduler import dispatch_pending
    result4b = dispatch_pending()
    emails_dispatched = result4b.get("dispatched", 0)
    emails_skipped = result4b.get("skipped", 0)
    emails_failed = result4b.get("failed", 0)
except Exception:
    logger.exception("step 4b: unhandled exception — dispatch_pending did not honour no-raise contract")
```

`emit_cycle_summary()` signature is extended to include `emails_scheduled`,
`emails_dispatched`, `emails_skipped`, `emails_failed` (new optional fields; CycleLogger
adds them to the JSON line if non-zero, drops them if all zero to preserve backward
compatibility with existing log parsers).

### 005/006 → 007 (server.py new routes)

Four new routes registered in `server.py`:

```python
from openclaw_gateway.routes.email_api import (
    api_approve_email,
    api_cancel_email,
    api_list_emails,
    api_list_email_events,
)

mcp.custom_route("/api/emails", methods=["GET"])(api_list_emails)
mcp.custom_route("/api/emails/{email_id}/approve", methods=["POST"])(api_approve_email)
mcp.custom_route("/api/emails/{email_id}/cancel", methods=["POST"])(api_cancel_email)
mcp.custom_route("/api/email-events", methods=["GET"])(api_list_email_events)
```

Handlers live in `src/openclaw_gateway/routes/email_api.py` (new file, mirrors `api.py`
pattern). They call `email_scheduler.queue_store.get_store()` (singleton) for reads,
and `await asyncio.to_thread(store.approve, email_id)` for writes.

---

## Implementation Strategy

1. **Phase 1 — Core package** (no side effects): `models.py`, `config.py`, `template.py` — fully testable in isolation.
2. **Phase 2 — State layer** (file I/O): `queue_store.py`, `audit_logger.py`, `auth.py` — unit-testable with tmp dirs.
3. **Phase 3 — Scheduling logic**: `scheduler.py` (`is_business_hours()`, `next_window()`, `schedule_for_deal()`, `dispatch_pending()`) — unit-testable with mocked Gmail API + queue_store.
4. **Phase 4 — Integration**: `__init__.py` public API; `runner.py` step 4; gateway `email_api.py` handlers + `server.py` routes.
5. **Phase 5 — Dashboard UI**: 2 new panels in `dashboard.html` (email queue + audit history).
6. **Phase 6 — Integration tests**: end-to-end cycle tests with mocked Gmail API.

Each phase is independently deliverable and testable. MVP = Phases 1–3 (scheduling + file state), without dashboard UI.

---

## ADR Suggestions

📋 Architectural decision detected: **Gmail API send vs raw SMTP for outbound email** — Document rationale and scope implications? Run `/sp.adr gmail-api-send-vs-smtp`

📋 Architectural decision detected: **In-process email dispatcher vs separate daemon** — Document threading model and dispatch-latency tradeoff? Run `/sp.adr email-dispatch-threading-model`
