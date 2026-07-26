# Email Scheduler API Contracts: 007-email-scheduling

**Date**: 2026-07-26 | **Branch**: `007-email-scheduling`
**Base URL**: `http://127.0.0.1:18790`

Four new REST endpoints added to the existing `openclaw_gateway`. All handlers live in
`src/openclaw_gateway/routes/email_api.py`. All responses include `Access-Control-Allow-Origin: *`.

---

## POST /api/emails/{email_id}/approve

Approve a scheduled email for dispatch at the next eligible business-hours window.

**Path parameter**: `email_id` — UUID4 string matching `ScheduledEmail.id`.

**Request body**: Empty (`{}` or no body). No fields required.

**Responses**:

```
200 OK  — approval succeeded (or email was already approved — idempotent)
{
  "id": "<uuid>",
  "status": "approved",
  "approved_at": "2026-07-26T10:15:00Z"
}

404 Not Found  — no email entry with this id
{
  "error": "not_found",
  "email_id": "<uuid>"
}

409 Conflict  — email is in a terminal state that cannot transition to approved
{
  "error": "invalid_transition",
  "email_id": "<uuid>",
  "current_status": "sent",
  "requested": "approve"
}
Terminal statuses that produce 409 on approve: "sent", "cancelled", "failed"

500 Internal Server Error  — queue write failed (disk full, permissions error)
{
  "error": "state_write_failed",
  "detail": "<OS error message>"
}
On 500: no state change is persisted; in-memory state is rolled back to pre-request value.
```

**Idempotency**: Calling approve on an already-approved email returns `200` with the
existing `approved_at` timestamp. Not an error.

**Side effect**: Writes an `approved` audit event to `email_audit.log` (actor: `"operator"`).
If the audit write fails, the state change IS still committed; the failure is logged to
`pipeline.log` as `[WARN] audit_write_failed`.

**Implementation**: `await asyncio.to_thread(store.approve, email_id)` — serialised by
`threading.Lock` inside `EmailQueueStore.approve()`.

---

## POST /api/emails/{email_id}/cancel

Cancel a scheduled or approved email. Prevents it from being dispatched.

**Path parameter**: `email_id` — UUID4 string.

**Request body**: Empty.

**Responses**:

```
200 OK  — cancellation succeeded (or email was already cancelled — idempotent)
{
  "id": "<uuid>",
  "status": "cancelled",
  "cancelled_at": "2026-07-26T10:20:00Z"
}

200 OK  — cancelling a "failed" email is permitted (not an error)
{
  "id": "<uuid>",
  "status": "cancelled",
  "cancelled_at": "2026-07-26T10:21:00Z"
}
Note: failed_at, retry_count, last_error, retry_after are preserved as-is.

404 Not Found  — no email entry with this id
{
  "error": "not_found",
  "email_id": "<uuid>"
}

409 Conflict  — email already sent; cannot cancel after dispatch
{
  "error": "invalid_transition",
  "email_id": "<uuid>",
  "current_status": "sent",
  "requested": "cancel"
}
The only terminal status that produces 409 on cancel is "sent".

500 Internal Server Error  — queue write failed
{
  "error": "state_write_failed",
  "detail": "<OS error message>"
}
```

**Idempotency**: Calling cancel on an already-cancelled email returns `200`. Not an error.

**Side effect**: Writes a `cancelled` audit event (actor: `"operator"`).

---

## GET /api/emails

Returns the email queue, optionally filtered by status.

**Query parameters**:

| Parameter | Type | Default | Constraints |
|---|---|---|---|
| `status` | string | `"all"` | `scheduled \| approved \| sent \| cancelled \| failed \| all` |
| `limit` | integer | `50` | 1–200; values > 200 silently clamped to 200 |
| `offset` | integer | `0` | ≥ 0; if offset ≥ total, returns empty `emails` array |

**Responses**:

```
200 OK
{
  "emails": [
    {
      "id": "<uuid>",
      "gmail_message_id": "18f3a1b2c3d4e5f6",
      "recipient_name": "James Harrington",
      "recipient_email": "james@harrington-consulting.co.uk",
      "subject": "Following up on your enquiry about IT upgrade",
      "body": "Hi James,\n\nThank you for...",
      "status": "scheduled",
      "proposed_send_at": "2026-07-28T09:00:00Z",
      "created_at": "2026-07-26T09:00:00Z",
      "approved_at": null,
      "sent_at": null,
      "cancelled_at": null,
      "failed_at": null,
      "retry_count": 0,
      "retry_after": null,
      "last_error": null
    }
  ],
  "total": 1,
  "offset": 0
}
Note: "total" is the count of records matching the applied status filter,
      not the full queue size. E.g., if status=scheduled and 3 emails are
      scheduled out of 10 total, total=3.

400 Bad Request  — unrecognised status value
{
  "error": "invalid_status",
  "valid_values": ["scheduled", "approved", "sent", "cancelled", "failed", "all"]
}

500 Internal Server Error  — in-memory queue unavailable
{
  "error": "queue_read_failed",
  "detail": "<message>"
}
```

**Sort order**: `created_at` descending (newest first).

**Implementation**: Read-only from in-memory `EmailQueueStore`. No file I/O per request.
Does not require lock acquisition.

---

## GET /api/email-events

Returns the full audit log of email lifecycle events.

**Query parameters**:

| Parameter | Type | Default | Constraints |
|---|---|---|---|
| `limit` | integer | `100` | 1–500; values > 500 silently clamped to 500 |
| `offset` | integer | `0` | ≥ 0 |

**Responses**:

```
200 OK
{
  "events": [
    {
      "event_id": "<uuid>",
      "email_id": "<uuid>",
      "gmail_message_id": "18f3a1b2c3d4e5f6",
      "event_type": "approved",
      "timestamp": "2026-07-26T10:15:00Z",
      "actor": "operator",
      "recipient_email": "james@harrington-consulting.co.uk",
      "error_detail": null,
      "retry_count": null
    }
  ],
  "total": 42,
  "offset": 0
}
Note: "total" is the count of ALL events in the audit log (unfiltered — this
      endpoint has no event_type filter parameter). Pagination via limit/offset
      applies to this total.

500 Internal Server Error  — audit log unreadable or parse failure
{
  "error": "audit_read_failed",
  "detail": "<message>"
}
```

**Sort order**: `timestamp` descending (newest first).

**Implementation**: Reads from in-memory event cache populated at startup and updated
after each audit write. No file I/O per request after startup.

---

## Orchestrator Integration Contract (004 → 007)

### schedule_for_deal(deal_payload: dict) → dict

Called by `pipeline_orchestrator.runner.run_cycle()` in step 4a, once per deal in
`result1["deals_extracted"]`.

**Input** (`deal_payload` dict):

| Key | Type | Source in result1 |
|---|---|---|
| `gmail_message_id` | `str` | `deal["message_id"]` |
| `sender_email` | `str \| None` | `deal["sender_email"]` |
| `sender_name` | `str \| None` | `deal["sender_name"]` |
| `subject` | `str \| None` | `deal["subject"]` |
| `company_name` | `str \| None` | `deal["company_name"]` |
| `deal_summary` | `str \| None` | `deal["summary"]` |

**Return** (always a dict — MUST NOT raise):

| `status` | `reason` | When |
|---|---|---|
| `"scheduled"` | `""` | New entry created |
| `"skipped"` | `"duplicate"` | Active entry (scheduled/approved/sent) already exists |
| `"skipped"` | `"no_recipient"` | `sender_email` absent or invalid; `no-recipient` audit event written |
| `"skipped"` | `"not_discord_notified"` | Deal has not yet reached `discord-notified` status in the state store |
| `"error"` | `"<message>"` | Internal exception; `scheduler-error` audit event written before return |

**No-raise guarantee**: All exceptions are caught internally. `pipeline_orchestrator` is
responsible only for logging `[WARN] scheduler-error: <reason>` when `status == "error"`.
A belt-and-suspenders `try/except` in runner.py is present but the return-value path is
primary.

### dispatch_pending() → dict

Called by `run_cycle()` in step 4b, once per cycle regardless of how many deals were processed.

**Input**: None.

**Return** (always a dict — MUST NOT raise):

```python
{
  "dispatched": int,   # emails successfully sent this cycle
  "skipped": int,      # approved emails not yet eligible (hours gate or retry_after)
  "failed": int        # approved emails that received a send attempt and failed
}
```

**No-raise guarantee**: All internal exceptions are caught, logged to `pipeline.log`, and
recorded as `scheduler-error` audit events before returning.
