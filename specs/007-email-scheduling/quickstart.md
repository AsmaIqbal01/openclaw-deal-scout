# Quickstart: Email Scheduling & Smart Send-Time Optimization (007)

**Date**: 2026-07-26 | **Branch**: `007-email-scheduling`

Manual test scenarios for all four user stories. Run after implementation against a
local gateway (`http://127.0.0.1:18790`). Each scenario can be validated with a
combination of `GET /api/emails`, `GET /api/email-events`, and inspection of
`email_queue.json` and `email_audit.log`.

**Prerequisites**:
- Gateway running: `python -m openclaw_gateway`
- `.env` contains: `STATE_STORE_PATH`, `GMAIL_CREDENTIALS_PATH`, `EMAIL_FROM_ADDRESS`
- `token.json` includes `https://www.googleapis.com/auth/gmail.send` scope
- A `processed_ids.json` with at least one entry at `status: "discord-notified"` for testing

---

## Scenario 1 — Auto-schedule on deal detection (US1)

**Goal**: Verify that a deal reaching `discord-notified` produces a `"scheduled"` queue entry.

**Steps**:
1. Add a test deal to `processed_ids.json` with `status: "discord-notified"` and a valid `sender_email`.
2. Run a pipeline cycle: `POST http://127.0.0.1:18790/api/run-cycle`
3. `GET http://127.0.0.1:18790/api/emails?status=scheduled`

**Expected**: Response contains at least one entry with `status: "scheduled"`, `sent_at: null`,
and `recipient_email` matching the deal's `sender_email`. Audit log has a `scheduled` event.

**Negative case**: Add a deal with no `sender_email` (or an invalid one such as `"notanemail"`).
Run cycle. `GET /api/emails` should NOT contain a new entry for that deal. `GET /api/email-events`
should contain a `no-recipient` event with the correct `gmail_message_id`.

---

## Scenario 2 — Operator approval gate (US2)

**Goal**: Verify approve and cancel flows; verify idempotency.

**Steps**:
1. Confirm at least two `"scheduled"` entries exist from Scenario 1 (or add test entries to `email_queue.json` directly).
2. Approve one: `POST http://127.0.0.1:18790/api/emails/<id1>/approve`
   - Expected: `200 {"id": "<id1>", "status": "approved", "approved_at": "<timestamp>"}`
3. Cancel another: `POST http://127.0.0.1:18790/api/emails/<id2>/cancel`
   - Expected: `200 {"id": "<id2>", "status": "cancelled", "cancelled_at": "<timestamp>"}`
4. Approve the same email again: `POST /api/emails/<id1>/approve`
   - Expected: `200` with the SAME `approved_at` timestamp (idempotent).
5. Cancel the already-cancelled email: `POST /api/emails/<id2>/cancel`
   - Expected: `200` (idempotent — no error).
6. Try to approve a terminal email: `POST /api/emails/<id2>/cancel` then try `POST /api/emails/<id2>/approve`
   - Expected: `409 {"error": "invalid_transition", "current_status": "cancelled", "requested": "approve"}`
7. `GET /api/email-events`
   - Expected: `approved` event for id1, `cancelled` event for id2, both with `actor: "operator"`.
8. Open dashboard (http://127.0.0.1:18790). Verify email panel shows remaining `"scheduled"` entries.

---

## Scenario 3 — Smart send-time (UK business hours) (US3)

**Goal**: Verify dispatch happens only within Mon–Fri 09:00–17:00 Europe/London.

**Prerequisite**: An approved email exists in the queue (`status: "approved"`).

**Case A — Inside business hours**:
1. Set system clock (or mock `datetime.now()` in tests) to Tuesday 10:00 Europe/London.
2. Run a pipeline cycle: `POST /api/run-cycle`
3. `GET /api/emails?status=sent` — Expected: email appears with `sent_at` between 10:00 and 17:00 Tuesday.
4. `GET /api/email-events` — Expected: `sent` event with `actor: "system"`.

**Case B — Outside business hours (weekend)**:
1. Approve an email. Set time to Saturday 14:00 Europe/London.
2. Run cycle. `GET /api/emails?status=sent` — Expected: email NOT in sent list.
3. `GET /api/emails?status=approved` — Expected: email still approved (skipped this cycle).
4. Advance time to Monday 09:05 Europe/London. Run cycle.
   - Expected: email now appears in `status: "sent"`.

**Case C — DST boundary (BST test)**:
1. Approve an email. Set time to 08:15 UTC on a day when BST is active (April–October).
   08:15 UTC = 09:15 BST — inside the window.
2. Run cycle. Expected: email dispatched (09:15 BST is inside 09:00–17:00).

**Case D — Retry on SMTP failure** (unit test scenario):
1. Mock Gmail API to return `HttpError(status=500, reason="Server Error")`.
2. Approve an email. Run cycle (first failure).
   - Expected: `status` stays `"approved"`, `retry_count: 1`, `retry_after` set to approx. `now + 60s`.
3. Run cycle before `retry_after` elapses. Expected: dispatch skipped (counted as `skipped`, not `failed`).
4. Advance time past `retry_after`. Run cycle (second failure).
   - Expected: `retry_count: 2`, new `retry_after` ≈ `now + 120s`.
5. After third failure: `retry_count: 3`, `status: "failed"`, `retry_after: null`.
   - `GET /api/email-events` — Expected: three `failed` events, third one with `retry_count: 3`.
   - Check `pipeline.log` for `[WARN]` entry.

---

## Scenario 4 — Full audit trail (US4)

**Goal**: Walk a single email through all lifecycle events and verify the audit trail.

**Steps**:
1. Run a pipeline cycle to produce a `"scheduled"` email. Note the `email_id`.
2. Verify `GET /api/email-events` contains `{"event_type": "scheduled", "actor": "system"}`.
3. Approve the email: `POST /api/emails/<id>/approve`.
4. Verify `GET /api/email-events` contains `{"event_type": "approved", "actor": "operator"}`.
5. Run cycle during business hours to dispatch the email.
6. Verify `GET /api/email-events` contains `{"event_type": "sent", "actor": "system"}`.
7. Open dashboard history panel. Verify all three events appear in reverse-chronological order.

**Second flow — cancel**:
1. Schedule a second email (new deal). Note `email_id`.
2. `GET /api/email-events` — verify `scheduled` event.
3. Cancel: `POST /api/emails/<id2>/cancel`.
4. `GET /api/email-events` — verify `cancelled` event with `actor: "operator"`.
5. Total events for id2: 2 (scheduled, cancelled).

**Audit log inspection** (direct file check):
```bash
tail -20 /path/to/email_audit.log | python3 -c "
import sys, json
for line in sys.stdin:
    e = json.loads(line)
    print(e['event_type'], e['actor'], e['timestamp'])
"
```
Expected output shows all transitions in chronological order.

---

## Scenario 5 — Startup recovery (Edge case)

**Goal**: Verify recovery mechanism when process crashes between SMTP confirm and queue write.

**Steps** (unit test scenario):
1. Set up queue with an email at `status: "approved"`.
2. Write a `sent` audit event for that email to `email_audit.log` directly (simulating SMTP
   confirmed but queue write crashed before commit).
3. Restart the `EmailQueueStore` (reinitialise from file). In-memory queue should still show
   `status: "approved"` (the file was not updated before the crash).
4. Call `_repair_from_audit()`.
5. Verify: queue entry now has `status: "sent"`. A `recovered` audit event is written.

---

## Scenario 6 — Existing tests remain green

**Goal**: Verify all 321 pre-existing tests pass after 007 implementation.

```bash
pytest tests/ -x --ignore=tests/integration/test_email_scheduling_e2e.py -q
```

Expected: all 321 tests pass. Zero regressions.

Then run the full suite including new email scheduler tests:
```bash
pytest tests/ -q
```

Expected: all new tests pass; final count > 321.
