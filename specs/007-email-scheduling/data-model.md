# Data Model: Email Scheduling & Smart Send-Time Optimization (007)

**Date**: 2026-07-26 | **Branch**: `007-email-scheduling`

---

## Entities

### ScheduledEmail

Stored in `email_queue.json` as elements of the `"emails"` array.

| Field | Python type | Required | Notes |
|---|---|---|---|
| `id` | `str` (UUID4) | required | Stable identity; never changes after creation |
| `gmail_message_id` | `str` | required | Deal key from 001-gmail-intake; deduplication key |
| `recipient_name` | `str \| None` | optional | From `sender_name`; null if absent |
| `recipient_email` | `str` | required | SMTP To address from `sender_email` |
| `subject` | `str` | required | Rendered per FR-009 subject-line rule |
| `body` | `str` | required | Plain-text body rendered from template |
| `status` | `EmailStatus` (enum str) | required | `scheduled \| approved \| sent \| cancelled \| failed` |
| `proposed_send_at` | `str` (ISO-8601 UTC) | required | Advisory; next business window at scheduling time |
| `created_at` | `str` (ISO-8601 UTC) | required | Scheduling timestamp |
| `approved_at` | `str \| None` | optional | Set when operator approves |
| `sent_at` | `str \| None` | optional | Set when SMTP send confirmed |
| `cancelled_at` | `str \| None` | optional | Set when operator cancels |
| `failed_at` | `str \| None` | optional | Most recent failure timestamp |
| `retry_count` | `int` (0–3) | required | Send attempts made; starts at 0 |
| `retry_after` | `str \| None` | optional | Earliest UTC to attempt next retry; null when not retrying |
| `last_error` | `str \| None` | optional | Error from most recent failed send |

**Python dataclass**:
```python
@dataclass
class ScheduledEmail:
    id: str
    gmail_message_id: str
    recipient_name: str | None
    recipient_email: str
    subject: str
    body: str
    status: str          # EmailStatus enum value
    proposed_send_at: str
    created_at: str
    approved_at: str | None = None
    sent_at: str | None = None
    cancelled_at: str | None = None
    failed_at: str | None = None
    retry_count: int = 0
    retry_after: str | None = None
    last_error: str | None = None
```

**Status enum**:
```python
class EmailStatus(str, Enum):
    SCHEDULED  = "scheduled"
    APPROVED   = "approved"
    SENT       = "sent"
    CANCELLED  = "cancelled"
    FAILED     = "failed"
```

---

### EmailEvent

Stored as JSONL in `email_audit.log` (append-only; one JSON object per line).

| Field | Python type | Required | Notes |
|---|---|---|---|
| `event_id` | `str` (UUID4) | required | Unique per event |
| `email_id` | `str \| None` | optional | References `ScheduledEmail.id`; null for no-recipient/scheduler-error |
| `gmail_message_id` | `str \| None` | required | Null only when incoming payload missing the key (scheduler-error) |
| `event_type` | `EventType` (enum str) | required | See enum below |
| `timestamp` | `str` (ISO-8601 UTC) | required | Event occurrence time |
| `actor` | `str` | required | `"operator"` or `"system"` |
| `recipient_email` | `str \| None` | optional | Absent for no-recipient and scheduler-error |
| `error_detail` | `str \| None` | optional | Present on `failed` and `scheduler-error` |
| `retry_count` | `int \| None` | optional | Present on `failed` events |

**Event type enum**:
```python
class EventType(str, Enum):
    SCHEDULED       = "scheduled"
    APPROVED        = "approved"
    CANCELLED       = "cancelled"
    SENT            = "sent"
    FAILED          = "failed"
    NO_RECIPIENT    = "no-recipient"
    DUPLICATE       = "duplicate-skipped"
    SCHEDULER_ERROR = "scheduler-error"
    RECOVERED       = "recovered"
    RECOVERY_WARN   = "recovery-warning"
```

---

## File Structures

### email_queue.json

```json
{
  "version": 1,
  "emails": [
    {
      "id": "e7f3a1b2-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
      "gmail_message_id": "18f3a1b2c3d4e5f6",
      "recipient_name": "James Harrington",
      "recipient_email": "james@harrington-consulting.co.uk",
      "subject": "Following up on your enquiry about IT infrastructure upgrade",
      "body": "Hi James,\n\nThank you for getting in touch...",
      "status": "approved",
      "proposed_send_at": "2026-07-28T09:00:00Z",
      "created_at": "2026-07-25T14:32:11Z",
      "approved_at": "2026-07-25T14:45:03Z",
      "sent_at": null,
      "cancelled_at": null,
      "failed_at": null,
      "retry_count": 0,
      "retry_after": null,
      "last_error": null
    }
  ]
}
```

### email_audit.log (JSONL)

Each line is a JSON object:
```json
{"event_id":"a1b2...","email_id":"e7f3...","gmail_message_id":"18f3...","event_type":"scheduled","timestamp":"2026-07-25T14:32:11Z","actor":"system","recipient_email":"james@harrington-consulting.co.uk","error_detail":null,"retry_count":null}
{"event_id":"b2c3...","email_id":"e7f3...","gmail_message_id":"18f3...","event_type":"approved","timestamp":"2026-07-25T14:45:03Z","actor":"operator","recipient_email":"james@harrington-consulting.co.uk","error_detail":null,"retry_count":null}
```

---

## State Machine — ScheduledEmail.status

```
                    schedule_for_deal()
                          │
                          ▼
                     [scheduled] ◄── created by step 4a
                       │    │
          operator      │    │ operator
          approve()     │    │ cancel()
                       │    │
                       ▼    ▼
                  [approved] [cancelled] ← terminal
                       │
           dispatch_pending() runs:
                       │
           ┌───────────┼───────────────────────────────┐
           │           │                               │
           │  business hours open,                     │
           │  retry_after elapsed                      │
           │           │                               │
           │    SMTP send attempt                      │
           │           │                               │
      SMTP ok     SMTP fail                      business hours
           │       (retry_count < 3)            closed OR retry_after
           │           │                         not elapsed
           ▼           ▼                               │
        [sent]    status stays [approved]        (skipped this cycle)
       terminal   retry_count++, retry_after set
                       │
                  retry_count == 3
                       │
                       ▼
                   [failed] ← terminal (but can be manually cancelled)
                       │
                  operator cancel()
                       │
                       ▼
                  [cancelled] ← terminal
```

**Terminal statuses**: `sent`, `cancelled`.
**Quasi-terminal**: `failed` — terminal for dispatch but can be cancelled by operator.

### Transition → Audit Event Map

| Transition | Actor | EventType |
|---|---|---|
| New entry created | system | `scheduled` |
| approved | operator | `approved` |
| cancelled (from scheduled/approved/failed) | operator | `cancelled` |
| SMTP confirmed | system | `sent` |
| SMTP failed (retry < 3) | system | `failed` (with retry_count) |
| SMTP failed (retry = 3 — terminal) | system | `failed` (retry_count: 3) |
| `sender_email` absent/invalid — skip | system | `no-recipient` |
| `gmail_message_id` duplicate (active status) | system | `duplicate-skipped` |
| Internal exception in `schedule_for_deal()` | system | `scheduler-error` |
| Startup: queue entry repaired from audit | system | `recovered` |
| Startup: audit log corrupted — reset | system | `recovery-warning` |

---

## Validation Rules

**sender_email validity** (FR-008): A string is valid if it contains exactly one `@`, a
non-empty local-part before it, and a non-empty domain after it that contains at least one `.`.

```python
def _is_valid_email(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    parts = value.split('@')
    if len(parts) != 2:
        return False
    local, domain = parts
    return bool(local) and '.' in domain and bool(domain.split('.')[-1])
```

**Field absence definition** (FR-009): A field is absent if it is `None`, missing from the
dict, or a string that is empty or whitespace-only after `.strip()`.

```python
def _is_present(value) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())
```

---

## Deduplication Logic (FR-014)

Active-status check before creating a new `ScheduledEmail`:

```python
ACTIVE_STATUSES = {"scheduled", "approved", "sent"}

def _find_active(emails: list[ScheduledEmail], gmail_message_id: str) -> ScheduledEmail | None:
    return next(
        (e for e in emails if e.gmail_message_id == gmail_message_id
                            and e.status in ACTIVE_STATUSES),
        None
    )
```

| Existing entry status | Action |
|---|---|
| `scheduled` | Skip; write `duplicate-skipped` event |
| `approved` | Skip; write `duplicate-skipped` event |
| `sent` | Skip permanently; write `duplicate-skipped` event |
| `cancelled` | Create new entry (operator intent: revisit) |
| `failed` | Create new entry (technical retry after investigation) |
| None (no entry) | Create new entry |

Old `cancelled`/`failed` entries are retained alongside the new entry — never removed.
