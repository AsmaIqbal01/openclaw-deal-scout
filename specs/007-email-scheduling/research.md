# Research: Email Scheduling & Smart Send-Time Optimization (007)

**Date**: 2026-07-26 | **Branch**: `007-email-scheduling`

---

## R-001 — Gmail API send endpoint

**Decision**: Use `googleapiclient.discovery.build('gmail', 'v1', credentials=creds)` →
`service.users().messages().send(userId='me', body={'raw': raw_b64})`.

**Rationale**: Reuses `google-api-python-client` already present in the venv (pulled in by
`gmail_intake`). Handles OAuth2 token refresh natively via the same
`google.oauth2.credentials.Credentials` pattern as `gmail_intake.gmail_client.build_service()`.
Avoids manual XOAUTH2 base64 construction required for raw SMTP.

**Required scope**: `https://www.googleapis.com/auth/gmail.send` (minimally privileged; does
not grant inbox read access). The operator must re-run the OAuth consent flow once to add
this scope to `token.json` before the first email dispatch.

**Message construction**:
```python
from email.mime.text import MIMEText
import base64

msg = MIMEText(body, 'plain', 'utf-8')
msg['to'] = recipient_email
msg['from'] = from_address
msg['subject'] = subject
raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
service.users().messages().send(userId='me', body={'raw': raw}).execute()
```

**Error responses**:
- `HttpError 403` — token lacks `gmail.send` scope → treated as auth failure; counted as retry attempt
- `HttpError 429` — Gmail rate limit (500/day cap) → retriable; counts as failed send attempt
- `HttpError 5xx` — transient server error → retriable

**Alternatives considered**:
- `smtplib` + `SMTP.starttls()` (port 587) with XOAUTH2 — rejected: requires manual XOAUTH2
  string, no native refresh handling, adds ~50 lines of low-level auth code with no benefit.
- `yagmail` — rejected: external dependency; wraps smtplib; adds unnecessary abstraction layer.

---

## R-002 — DST-aware business-hours evaluation

**Decision**: `from zoneinfo import ZoneInfo; ZoneInfo("Europe/London")` — Python 3.9+ stdlib.

**Usage**:
```python
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

def is_business_hours(dt_utc: datetime) -> bool:
    london = dt_utc.astimezone(ZoneInfo("Europe/London"))
    return (
        london.weekday() < 5                   # Mon=0 … Fri=4
        and 9 <= london.hour < 17              # 09:00–16:59 inclusive
    )
```

**DST transition**: `ZoneInfo` reads from the system tzdata database. On Ubuntu 22.04,
`python3-tzdata` is available via apt and `zoneinfo` resolves `Europe/London` to BST (UTC+1)
between last Sunday of March and last Sunday of October. `datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/London"))` always returns the correct local time.

**Fallback**: If `ZoneInfoNotFoundError` is raised (tzdata package missing), fall back to UTC
and log `[WARN] zoneinfo_unavailable`. At UTC, 09:00–17:00 covers London winter hours; BST
emails will be slightly over-deferred (approved at 08:30 UTC in summer won't send until 09:00 UTC
rather than 09:00 BST). This is safe — emails are deferred, not sent early.

**next_business_window(from_dt)**: Compute the next open window from an arbitrary UTC datetime:
1. Convert to London time.
2. If Mon–Fri and 09:00 ≤ hour < 17:00 → return `from_dt` (already open).
3. If Mon–Fri and hour ≥ 17:00 → advance to next weekday at 09:00.
4. If Mon–Thu and hour < 09:00 → return same day at 09:00.
5. If Fri and hour ≥ 17:00, or Sat, or Sun → advance to next Monday at 09:00.

Return value is a UTC `datetime` representing the start of the next open window. The
`proposed_send_at` field on `ScheduledEmail` stores this value (advisory; recomputed from
`approved_at` at dispatch time).

**Alternatives considered**: `pytz` — functional equivalent but external dep; rejected per
zero-new-dependency constraint.

---

## R-003 — Threading model: queue writes from multiple contexts

**Problem**: `email_queue.json` is written from two concurrent contexts:
1. **Scheduler thread** (runs in `ThreadPoolExecutor` via `run_in_executor`) — `schedule_for_deal()`, `dispatch_pending()`
2. **Asyncio event loop** (Uvicorn/Starlette coroutines) — `POST /api/emails/{id}/approve`, `POST /api/emails/{id}/cancel`

**Decision**: Single shared `threading.Lock` instance in `EmailQueueStore`. The scheduler
thread acquires it directly (blocking, brief). HTTP handlers use
`await asyncio.to_thread(store._write_locked, ...)` to offload lock acquisition to the
thread pool, preventing event-loop blocking.

```python
class EmailQueueStore:
    def __init__(self): self._lock = threading.Lock()

    def approve(self, email_id: str) -> ScheduledEmail:
        with self._lock:
            # mutate in-memory, write atomically to disk
            ...

async def api_approve_email(request):
    store = get_store()
    result = await asyncio.to_thread(store.approve, email_id)
    return JSONResponse(result)
```

**Singleton pattern**: `get_store()` returns a module-level `_store: EmailQueueStore | None`
instance, initialized lazily on first call using `load_email_config()`. Same pattern as
pipeline_orchestrator's `_scheduler` module-level state.

**Alternatives considered**:
- `asyncio.Lock` — only works within a single event loop; scheduler thread is outside the
  event loop, so acquiring `asyncio.Lock` from the thread would require `asyncio.run_coroutine_threadsafe()`. More complex than `threading.Lock` + `asyncio.to_thread()`.
- `portalocker` — cross-process file locking; unnecessary since both paths are in-process.

---

## R-004 — Atomic write pattern for email_queue.json

**Decision**: Replicate `tempfile.NamedTemporaryFile` + `os.replace()` pattern used in
`pipeline_orchestrator.runner._write_store_raw()`.

```python
import os, tempfile, json

def _atomic_write(path: Path, data: dict) -> None:
    with tempfile.NamedTemporaryFile(
        mode='w', dir=str(path.parent), suffix='.tmp',
        delete=False, encoding='utf-8'
    ) as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp_path = fh.name
    os.replace(tmp_path, str(path))
```

`os.replace()` is atomic on POSIX filesystems (rename syscall). If the process crashes
after the Gmail send but before `os.replace()`, the in-flight entry retains `status: "approved"`
in the file, which triggers a retry on next cycle. This creates an at-least-once delivery
guarantee (acknowledged in spec Edge Cases section).

---

## R-005 — Audit log: Python logging vs raw file append

**Decision**: Python `logging.FileHandler` with `propagate=False`, one JSON object per line
(JSONL). Mirrors `CycleLogger` in `pipeline_orchestrator.cycle_logger`.

```python
class AuditLogger:
    def __init__(self, log_path: Path):
        self._logger = logging.getLogger("email_scheduler.audit")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        handler = logging.FileHandler(str(log_path), encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(message)s'))
        self._logger.addHandler(handler)

    def write(self, event: EmailEvent) -> None:
        self._logger.info(json.dumps(dataclasses.asdict(event)))
```

`logging.FileHandler` is thread-safe by default (uses an internal lock per handler).
No external locking needed for audit writes.

**Rotation**: Not applied in v1. `email_audit.log` is an immutable record; pruning requires
a future spec. At <20 events/day the file grows <1 KB/day — disk impact is negligible.

**Alternatives considered**: raw `open(path, 'a')` — not guaranteed thread-safe across
concurrent writes; requires an external lock; rejected.

---

## R-006 — email_scheduler package credential loading

**Decision**: `email_scheduler.auth.build_send_service(credentials_path: str)` — a self-contained
function replicating `gmail_intake.gmail_client.build_service()` but with `SEND_SCOPES`.

```python
SEND_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def build_send_service(credentials_path: str):
    token_path = os.path.join(os.path.dirname(os.path.abspath(credentials_path)), "token.json")
    try:
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            token_path, SEND_SCOPES
        )
    except Exception as exc:
        raise AuthError(str(exc)) from exc
    if creds.expired:
        if not creds.refresh_token:
            raise AuthError("credentials expired and no refresh token available")
        creds.refresh(google.auth.transport.requests.Request())
    return googleapiclient.discovery.build('gmail', 'v1', credentials=creds)
```

The send service is rebuilt on each `dispatch_pending()` call (not cached), ensuring the
latest token refresh is always used. The overhead of `googleapiclient.discovery.build()` is
a local dict read, not a network call (the discovery document is cached by the library).

**If `from_authorized_user_file` raises `google.auth.exceptions.MalformedError`** (scope not in
token): `dispatch_pending()` catches the `AuthError`, logs `[ERROR] gmail_send_auth_failed`,
marks the in-flight email's attempt as failed, and returns without dispatching. The operator
must run the one-time scope re-auth.

**No changes to 001-gmail-intake** — the `token.json` credential file is shared but each module
declares its own required scopes. After the one-time re-auth (which adds `gmail.send` to the
token), both `gmail_intake.gmail_client.build_service()` and `email_scheduler.auth.build_send_service()`
will work from the same `token.json`.

---

## R-007 — Startup recovery for email_queue.json and email_audit.log

**Scenario**: Process crashes between SMTP confirm and queue file write. On restart:
1. Load `email_queue.json` from disk → entry has `status: "approved"`, `retry_count: 0`.
2. Scan `email_audit.log` for `sent` events — find `email_id` with a `sent` event but queue
   entry is still `"approved"`.
3. Repair: set queue entry to `status: "sent"`, write `sent_at` from the audit event's `timestamp`.
4. Write a `recovered` audit event.

**Implementation**: `EmailQueueStore._repair_from_audit(audit_log_path)` — called once at
startup before the store is exposed to the rest of the application.

**email_audit.log corruption on startup**: Reset `AuditLogger` to a fresh file; write a
single `recovery-warning` event at the top. Existing `email_queue.json` state is unaffected.

---

## R-008 — Template rendering and field absence

**Decision**: `template.py` function `render_email(deal_payload, template_str)` → `(subject, body)`.
Fields are considered absent if they are `None`, missing from the dict, or a whitespace-only string
(after `.strip()`).

**Subject derivation** (per FR-009):
```python
summary = deal_payload.get("deal_summary", "")
subj = deal_payload.get("subject", "")
if summary and summary.strip():
    return f"Following up on your enquiry about {summary.strip()}"
elif subj and subj.strip():
    return f"Following up on: {subj.strip()}"
else:
    return "Following up on your enquiry"
```

**Body fallbacks**:
- `sender_name` absent → greeting = `"Hi there,"`
- `company_name` absent → omit company line
- `deal_summary` absent + `subject` absent → use `"your enquiry"` in body

Template substitution uses `str.format_map()` with a `defaultdict(str)` to silently
substitute empty string for any missing placeholder.
