# Feature Specification: Email Scheduling & Smart Send-Time Optimization

**Feature Branch**: `007-email-scheduling`
**Created**: 2026-07-25
**Status**: Draft — Revised (v21)

---

## Component Ownership

This feature touches three existing packages. Changes are bounded as follows:

| Component | Package | Change type |
|---|---|---|
| **007 (new)** | `email_scheduler` | New package — scheduling logic, `email_queue.json` state, send dispatch, audit log |
| **004 (modified)** | `pipeline_orchestrator.runner` | Add step 4: call `email_scheduler.schedule_for_deal()` after step 3 **succeeds** (i.e., only when the deal reaches `discord-notified` status) |
| **005/006 (modified)** | `openclaw_gateway` | Add two REST endpoints (`/api/emails/{id}/approve`, `/api/emails/{id}/cancel`); add email queue panel and audit history panel to `dashboard.html` |

No changes are required in 001, 002, or 003. No new processes or systemd units are introduced.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Auto-Schedule on Deal Detection (Priority: P1)

When the pipeline detects and fully processes a deal (Gmail → HubSpot → Discord complete), the system automatically creates a pending follow-up email addressed to the deal's original sender, identified by `gmail_message_id`. The email sits in a "scheduled" queue and does not send until the operator approves it.

**Why this priority**: Closes the gap between deal detection and action. Without this, every deal requires manual operator follow-up. This is the core value of the feature.

**Independent Test**: Run a pipeline cycle that produces a newly processed deal. Verify a scheduled email entry appears in `email_queue.json` with status `"scheduled"`, the correct recipient email address, and confirm no SMTP send has occurred.

**Acceptance Scenarios**:

1. **Given** a deal (identified by `gmail_message_id`) reaches `discord-notified` status, **When** the pipeline cycle's step 4 runs, **Then** an entry is written to `email_queue.json` within 60 seconds with `status: "scheduled"`, the correct `recipient_email`, and `sent_at: null`.
2. **Given** the deal payload contains no `sender_email` value or the value is not a valid email address, **When** step 4 runs, **Then** no entry is written to `email_queue.json` and a `no-recipient` audit event is written with the `gmail_message_id`.
3. **Given** an entry with `status` of `"scheduled"` or `"approved"` already exists for this `gmail_message_id`, **When** the same deal is reprocessed, **Then** no new entry is created and the existing entry is unchanged.

---

### User Story 2 — Operator Review & Approval Gate (Priority: P2)

The operator opens the dashboard and sees all pending emails awaiting approval. They can read the full email content and recipient details before deciding to approve or cancel. No email leaves the system without a deliberate operator action.

**Why this priority**: Safety gate — the operator must never be surprised by an outgoing email. Approval is mandatory; this story is what makes the feature safe to run in production.

**Independent Test**: With a scheduled email in the queue, open the dashboard, approve one email and cancel another. Verify: approved email status changes to `"approved"`, cancelled email status changes to `"cancelled"`, no SMTP send has occurred, and both changes are reflected in the dashboard within 5 seconds.

**Acceptance Scenarios**:

1. **Given** one or more emails with `status: "scheduled"`, **When** the operator views the dashboard email panel, **Then** each entry shows recipient name (or "Unknown" if absent), recipient email address, `gmail_message_id`, subject line, body preview, and estimated dispatch window.
2. **Given** a pending email is displayed, **When** the operator clicks Approve, **Then** `POST /api/emails/{id}/approve` returns `200` with `{"id": "...", "status": "approved", "approved_at": "<UTC ISO-8601>"}` and `email_queue.json` reflects `status: "approved"`.
3. **Given** a pending email is displayed, **When** the operator clicks Cancel, **Then** `POST /api/emails/{id}/cancel` returns `200` with `{"id": "...", "status": "cancelled", "cancelled_at": "<UTC ISO-8601>"}` and the email will never be sent.
4. **Given** an Approve or Cancel request is made for an email already in the target status, **When** the endpoint is called again, **Then** it returns `200` with the current state (idempotent — no error, no duplicate event).
5. **Given** no emails are pending, **When** the operator opens the email panel, **Then** the panel shows a clear "No pending emails" empty state.

---

### User Story 3 — Smart Send-Time (UK Business Hours) (Priority: P3)

Approved emails are held until the next UK business-hours window (Monday–Friday, 09:00–17:00 Europe/London, DST-aware) and then dispatched automatically via the existing Gmail account. Approved emails inside business hours dispatch at the next scheduler tick (within 15 minutes). Emails approved outside hours wait until the next opening.

**Why this priority**: Sending cold outreach at 3 AM reduces response rates and looks unprofessional. Business-hours delivery maximises the chance of a reply without requiring operator timing discipline.

**Independent Test**: Approve an email when Europe/London time is outside business hours (e.g., Friday 20:00 Europe/London). Verify the email is not sent at the next scheduler tick but is dispatched at or after 09:00 Monday Europe/London time (within one scheduler interval of 09:00 opening).

**Acceptance Scenarios**:

1. **Given** an email is approved at 10:30 Tuesday (Europe/London), **When** the scheduler next runs (within 15 minutes), **Then** the email is dispatched and `sent_at` is set to a UTC timestamp between 10:30 and 17:00 that day (Europe/London).
2. **Given** an email is approved at 19:00 Thursday (Europe/London), **When** the scheduler runs, **Then** the email is not sent; it is dispatched at the first scheduler tick on or after 09:00 Friday (Europe/London).
3. **Given** an email is approved at 16:50 Friday (Europe/London), **When** the scheduler runs, **Then** the email is dispatched before 17:00 Friday (still within the window).
4. **Given** an email is approved at 17:01 Friday (Europe/London), **When** the scheduler runs, **Then** the email is held over the weekend and dispatched at the first scheduler tick on or after 09:00 Monday (Europe/London).
5. **Given** it is BST (summer, Europe/London = UTC+1) and an email is approved at 08:15 UTC (= 09:15 BST, inside the window), **When** the scheduler runs, **Then** the email is dispatched — the system correctly identifies 09:15 BST as inside business hours rather than treating 08:15 UTC as outside it.
6. **Given** a send attempt fails (SMTP error, OAuth token error, or network timeout), **When** the failure is detected, **Then** the system waits the retry interval before retrying; after 3 consecutive failures the email is marked `"failed"`, a `failed` audit event is written, and a warning entry is appended to `pipeline.log`.

---

### User Story 4 — Full Audit Trail (Priority: P4)

Every lifecycle event for every email (scheduled, approved, sent, cancelled, failed, no-recipient) is recorded with a UTC timestamp, `gmail_message_id`, recipient address, and a fixed `"operator"` actor string (single-user system — no login exists, so actor is always `"operator"` for human-triggered events and `"system"` for automated events). The dashboard exposes this history.

**Why this priority**: Auditability is essential when the system sends communications on behalf of the business. Required for accountability and debugging.

**Independent Test**: Walk a single email through scheduled → approved → sent. Confirm three audit events appear with correct timestamps, `gmail_message_id`, and actor values. Cancel a second email and confirm two events (scheduled, cancelled) appear.

**Acceptance Scenarios**:

1. **Given** an email undergoes any status transition, **When** the transition completes, **Then** an audit event is written within 5 seconds containing: `event_type`, `email_id`, `gmail_message_id`, `recipient_email`, `timestamp` (UTC ISO-8601), `actor` (`"operator"` or `"system"`), and `error_detail` (string or null).
2. **Given** the operator opens the dashboard history panel, **When** the panel loads, **Then** all audit events are shown in reverse-chronological order with all fields visible.
3. **Given** all 3 send retries are exhausted, **When** the `failed` event is written, **Then** the audit entry includes `error_detail` with the last error message and `retry_count: 3`.

---

### Edge Cases

- **Step 3 (Discord notification) fails**: `schedule_for_deal()` is not called; no `email_queue.json` entry is created for this deal. The email scheduling cycle for this deal resumes on the next pipeline cycle that successfully completes step 3 and reaches `discord-notified` status.
- **Missing `gmail_message_id` in deal_payload**: If `deal_payload` is missing the `gmail_message_id` key or its value is `None`, `schedule_for_deal()` MUST return `{"status": "error", "reason": "missing_gmail_message_id"}` and write a `scheduler-error` audit event with `email_id: null` and `gmail_message_id: null`. No `email_queue.json` entry is created.
- **`email_queue.json` growth policy**: Terminal-status entries (`sent`, `cancelled`, `failed`) are retained indefinitely in v1. No archival, pruning, or rotation is performed. The `GET /api/emails` endpoint's pagination (`limit`, `offset`) is the mechanism for handling a large number of historical entries in the dashboard.
- **SMTP send confirmed but `email_queue.json` write subsequently fails (dispatch path)**: If `dispatch_pending()` receives a confirmed SMTP send response but the subsequent atomic queue write fails, the in-memory entry is immediately set to `status: "sent"` and held as such for the lifetime of the process. A `[WARN] dispatch_write_failed` line is appended to `pipeline.log` containing `email_id`, `gmail_message_id`, and the OS error. The file on disk retains `status: "approved"`; on the next process restart, the startup-recovery mechanism detects the mismatch (a `sent` event in `email_audit.log` but `"approved"` in the queue file) and corrects the file entry to `status: "sent"`. This constitutes an **at-least-once delivery guarantee**: a process crash between SMTP confirm and queue write creates a known duplicate-send risk on restart; this is accepted in v1 given the low-volume B2B context.
- **Missing recipient email**: `sender_email` is absent or malformed → step 4 skips scheduling; writes a `no-recipient` audit event with `gmail_message_id`; pipeline cycle continues normally.
- **Expired OAuth token at send time**: SMTP send fails with auth error → enters retry queue (counts as attempt 1 of 3). Before each retry attempt, the email scheduler loads `token.json` (co-located with `credentials.json`, same files used by 001-gmail-intake) and refreshes the token via the Google OAuth library if it is expired — the same pattern as `gmail_intake.gmail_client.build_service()`. If the refresh itself fails (no refresh token, or Google rejects the refresh), the attempt is counted as a failed send and retry logic proceeds normally. Note: if 007's SMTP send path needs to share the token-refresh logic with `gmail_intake.gmail_client`, the planner (in `/sp.plan`) must decide whether to extract `build_service`'s credential-loading/refresh steps into a shared utility or duplicate the pattern in 007 — this is a planning decision outside spec scope.
- **Multiple deals from the same contact**: Each deal has a distinct `gmail_message_id`, so each produces an independent scheduled email. Deduplication is per-deal, not per-contact.
- **Deal reprocessed after terminal status**: If a deal is reprocessed and an entry with `status: "sent"` already exists for the same `gmail_message_id`, step 4 skips creation and writes a `duplicate-skipped` event — no second email is ever sent for the same deal. If the existing entry is `"cancelled"` or `"failed"`, step 4 creates a fresh scheduled entry (cancelled = operator intent to revisit; failed = technical retry after investigation).
- **UK bank holiday**: Treated as a working day (Mon–Fri calendar only; no bank holiday lookup in v1).
- **Concurrent pipeline cycle and email send**: Email dispatch runs in the same process as the gateway but is independently triggered by the scheduler. A pipeline cycle running concurrently does not block or cancel an in-flight email send.
- **`email_queue.json` corrupted or missing on startup**: System logs a warning, initialises an empty in-memory queue, and writes a fresh `email_queue.json`. The pipeline state store (`processed_ids.json`) is unaffected.
- **Partial write failure — `email_queue.json` updated but process crashes before audit event**: On next startup, the email queue is read and any entry whose status lacks a corresponding audit event gets a synthetic `recovered` audit event logged, so the audit trail remains navigable.
- **Approve/cancel REST call returns network error after state is already mutated**: The endpoints are idempotent — a retry of the same action returns `200` with the current state, never a conflict error. The client dashboard retries on any non-`200` response.
- **Gmail daily send cap reached (500 emails/day)**: SMTP send returns a rate-limit error → treated as a retriable failure; the email re-enters the retry queue. If the cap persists across all 3 retries, the email is marked `"failed"` with `error_detail: "gmail_rate_limit"`.
- **DST boundary — clocks spring forward**: An email approved at 00:59 UTC on the day clocks change to BST (last Sunday of March) is correctly evaluated using the Europe/London timezone; if the resulting local time is outside 09:00–17:00 BST, it is held.
- **Template variable missing — contact name absent**: Rendered as `"Hi there,"` in the email body. Missing `company_name` causes the company reference line to be omitted. Missing `deal_summary` falls back to the original email subject.
- **`email_audit.log` corrupted or inaccessible on startup**: System logs a warning to `pipeline.log`, starts a fresh `email_audit.log`, and writes a single `recovery-warning` event at the top noting that prior history may be unavailable. The gateway continues operating; existing `email_queue.json` state is unaffected.
- **`email_audit.log` append fails at runtime (process alive)**: If `email_audit.log` write returns an OS-level error (e.g. disk full, permissions change) during a live state transition (`approved`, `sent`, `failed`, etc.), the state change in `email_queue.json` is committed and NOT rolled back; a `[WARN] audit_write_failed` line is appended to `pipeline.log` containing `email_id`, `event_type`, and the OS error message. The missing audit event is reconstructed by the startup-recovery mechanism the next time the gateway restarts; no new field on `ScheduledEmail` is required.
- **Disk read error during `GET /api/emails` or `GET /api/email-events`**: Endpoint returns `500` with `{"error": "queue_read_failed" | "audit_read_failed", "detail": "<message>"}`. The dashboard shows an inline error state for the affected panel without affecting other panels.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automatically create a `"scheduled"` entry in `email_queue.json` when a deal's `gmail_message_id` reaches `discord-notified` status and 004-pipeline-orchestrator completes step 3.
- **FR-002**: System MUST NOT dispatch any email via SMTP until the entry's status has been set to `"approved"` by an explicit operator action.
- **FR-003**: The dashboard email panel MUST display all entries with `status: "scheduled"` or `status: "approved"` (i.e., all emails awaiting or eligible for dispatch), showing: `recipient_name` (or `"Unknown"`), `recipient_email`, `gmail_message_id`, `subject`, a plain-text body preview (first 200 characters), `status`, and `proposed_send_at`. The operator may approve or cancel any entry visible in this panel.
- **FR-004**: `POST /api/emails/{id}/approve` MUST set `status` to `"approved"`, record `approved_at` (UTC), write an `approved` audit event, and return `200` with the updated record. The operation MUST be idempotent.
- **FR-005**: `POST /api/emails/{id}/cancel` MUST set `status` to `"cancelled"`, record `cancelled_at` (UTC), write a `cancelled` audit event, and return `200` with the updated record. The operation MUST be idempotent. When cancelling a `"failed"` email, `failed_at`, `retry_count`, `last_error`, and `retry_after` are preserved as-is — they are a historical record of what happened and are not reset on the `failed → cancelled` transition.
- **FR-006**: System MUST dispatch approved emails only during Mon–Fri, 09:00–17:00 Europe/London, evaluated using the DST-aware Europe/London timezone (not a fixed UTC offset). Dispatch latency after the window opens is at most one scheduler interval (≤15 minutes).
- **FR-007**: System MUST send email via the existing Gmail account using the existing OAuth2 credentials. No additional accounts or third-party email services are permitted.
- **FR-008**: System MUST populate `recipient_email` from the `sender_email` field of the deal payload delivered by 004-pipeline-orchestrator at the end of step 3. If `sender_email` is absent or invalid, the email is not scheduled (see FR-016). **Validity rule**: `sender_email` is considered valid if and only if it is a non-empty string containing exactly one `"@"` character with a non-empty local-part before it and a non-empty domain after it that contains at least one `"."`. Any value that does not satisfy this rule (including `None`, empty string, or strings with no `@` or no `.` in the domain) is treated as invalid.
- **FR-009**: System MUST render the email body and subject line from a fixed plain-text template using available deal fields.

  **Subject-line derivation rule** (applies regardless of whether a custom template file is used):
  - If `deal_summary` is present and non-empty: subject = `"Following up on your enquiry about {deal_summary}"`
  - If `deal_summary` is absent or empty but `deal_payload.subject` is present and non-empty: subject = `"Following up on: {subject}"`
  - If both are absent or empty: subject = `"Following up on your enquiry"` (hardcoded literal)

  **Body template fallback rules**: A field is considered absent for the purposes of these fallback rules if it is missing from the dict, is `None`, or is a string that is empty or contains only whitespace after stripping. If `sender_name` is absent (by this definition), render `"Hi there,"` as the greeting; if `company_name` is absent, omit the company reference line; if `deal_summary` is absent, substitute the original email `subject` field (which is also subject to the same absence definition — if `subject` is also absent, use `"your enquiry"` as the substitution).

  The body template is a plain-text file whose path is given by the `EMAIL_TEMPLATE_PATH` environment variable; if the variable is unset, the file is unreadable, or the file is readable but yields an empty or whitespace-only string after stripping, the built-in default template is used verbatim (with `{placeholder}` values substituted per the fallback rules above):
  ```
  Hi {sender_name},

  Thank you for getting in touch regarding {deal_summary}.

  We'd love to explore this further — could we schedule a brief call at your convenience?

  Best regards
  ```
  Template content is not editable via a UI.
- **FR-010**: System MUST retry failed SMTP send attempts up to 3 times using a `retry_after` timestamp stored on the `ScheduledEmail` entry. On each failure, `ScheduledEmail.failed_at` is set to the UTC instant of the failure, and `retry_after` is computed as: first failure → `failed_at + 60 s`, second failure → `failed_at + 120 s`, third failure → `failed_at + 240 s`. The scheduler skips dispatch for an entry until `now ≥ retry_after`; effective minimum gap between retries is one scheduler interval (up to 15 minutes). After 3 failures the email is marked `"failed"`, `retry_after` is set to `null`, and a warning is appended to `pipeline.log`. **Retry state invariant**: between the first send failure and the exhaustion of all 3 retries, `status` remains `"approved"` — only `retry_count`, `retry_after`, `failed_at`, and `last_error` are mutated on each failure. The transition to `"failed"` occurs exactly once, when `retry_count` reaches 3. **Successful-retry field state**: if a retry attempt succeeds (SMTP send confirmed) before all 3 retries are exhausted, `status` transitions to `"sent"` and `sent_at` is set to the UTC instant of the successful response; `retry_after` is set to `null`; `last_error`, `failed_at`, and `retry_count` are preserved as-is (historical record of prior failures — not cleared on success). Retry dispatch attempts are subject to the same UK business-hours gate as first-attempt dispatches (FR-006); `retry_after` is evaluated only after the business-hours window also permits dispatch.
- **FR-011**: System MUST record an audit event for every status transition: `scheduled`, `approved`, `cancelled`, `sent`, `failed`, `no-recipient`. Each event includes `actor: "operator"` (for approve/cancel) or `actor: "system"` (for all automated transitions). If the audit event write fails at runtime (e.g. disk full, permissions error), the state transition in `email_queue.json` MUST still be committed; the failed write MUST be logged to `pipeline.log` as `[WARN] audit_write_failed` (with `email_id`, `event_type`, and OS error), and the audit gap MUST be recovered on next startup by the existing recovery mechanism.
- **FR-012**: The dashboard MUST expose the pending email queue and the full audit history in the existing dashboard UI — no separate application or page is required.
- **FR-013**: `email_queue.json` MUST be written atomically (write to a `.tmp` file then rename) to prevent partial-write corruption, consistent with the `processed_ids.json` pattern used throughout the project. The file-level structure is `{"emails": [...], "version": 1}` where `emails` is the ordered list of `ScheduledEmail` objects; `version` is a fixed integer for future schema evolution. Concurrent write safety is governed by the threading concurrency model stated in Assumptions: all write operations MUST acquire the shared `threading.Lock` before mutating the in-memory queue or writing to disk.
- **FR-014**: System MUST prevent duplicate active emails per deal. The deduplication check scans `email_queue.json` for any entry whose `gmail_message_id` matches AND whose `status` is in `{"scheduled", "approved", "sent"}`. If any such active-status entry exists, step 4 skips creation:
  - `"scheduled"` or `"approved"` → skip; write a `duplicate-skipped` audit event.
  - `"sent"` → skip permanently; write a `duplicate-skipped` audit event. A deal that has already produced a sent email MUST NOT produce a second outgoing email on reprocessing.
  If no active-status entry exists, a new entry is created even if historical entries for the same `gmail_message_id` exist in `"cancelled"` or `"failed"` status — those old entries are **retained in `email_queue.json` as historical records** alongside the new entry; they are never replaced, archived, or removed.
- **FR-015**: All 321 existing unit tests MUST continue to pass without modification after this feature is implemented.
- **FR-016**: When scheduling is skipped because `sender_email` is absent or invalid, the system MUST write a `no-recipient` audit event containing the `gmail_message_id` so the skip is visible in the dashboard history.
- **FR-017**: 007 email-scheduler owns the entire audit trail. When `schedule_for_deal()` encounters an internal failure, it MUST write the `scheduler-error` audit event internally (before returning) and then return `{"status": "error", "reason": "<message>"}`. 004-pipeline-orchestrator is responsible only for logging the `reason` to `pipeline.log` as `[WARN] scheduler-error` when it receives `{"status": "error"}`. A belt-and-suspenders `try/except` MAY be present at the step-4 call site to guard against future contract violations, but the return-value path is primary. In all cases, the error MUST NOT propagate to terminate the gateway process. No `email_queue.json` entry is created when `schedule_for_deal()` returns `{"status": "error"}`.

### Key Entities

**`ScheduledEmail`** — one row in the `email_queue.json` `"emails"` array:

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string (UUID) | required | Unique stable ID for this email entry |
| `gmail_message_id` | string | required | Canonical deal key from 001-gmail-intake; used for deduplication |
| `recipient_name` | string or null | optional | Contact's display name; null if absent |
| `recipient_email` | string | required | SMTP To address |
| `subject` | string | required | Email subject line — derived per FR-009 subject-line rule |
| `body` | string | required | Plain-text body (rendered from template + deal fields) |
| `status` | enum | required | `scheduled` / `approved` / `sent` / `cancelled` / `failed` |
| `proposed_send_at` | ISO-8601 UTC string | required | Estimated next UK business window at time of scheduling (advisory; actual dispatch computed from `approved_at`) |
| `created_at` | ISO-8601 UTC string | required | When the entry was created |
| `approved_at` | ISO-8601 UTC string or null | optional | When operator approved; null until approved |
| `sent_at` | ISO-8601 UTC string or null | optional | When SMTP send succeeded |
| `cancelled_at` | ISO-8601 UTC string or null | optional | When operator cancelled |
| `failed_at` | ISO-8601 UTC string or null | optional | UTC timestamp of the most recent send failure; null when no failure has occurred |
| `retry_count` | integer (0–3) | required | Number of send attempts made; starts at 0 |
| `retry_after` | ISO-8601 UTC string or null | optional | Earliest UTC time the scheduler may attempt the next retry; null when not in a retry state |
| `last_error` | string or null | optional | Error message from most recent failed send attempt |

**Example record**:
```json
{
  "id": "e7f3a1b2-4c5d-4e6f-9a0b-1c2d3e4f5a6b",
  "gmail_message_id": "18f3a1b2c3d4e5f6",
  "recipient_name": "James Harrington",
  "recipient_email": "james@harrington-consulting.co.uk",
  "subject": "Following up on your enquiry",
  "body": "Hi James,\n\nThank you for reaching out...",
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
```

**`EmailEvent`** — immutable audit log. Stored as a JSONL append-only file (`email_audit.log`) following the `pipeline.log` pattern:

| Field | Type | Required | Notes |
|---|---|---|---|
| `event_id` | string (UUID) | required | Unique per event |
| `email_id` | string (UUID) or null | optional | References `ScheduledEmail.id`; `null` for `no-recipient` and `scheduler-error` events where no queue entry was created |
| `gmail_message_id` | string or null | required | Canonical deal key; `null` only when the incoming `deal_payload` itself is missing the `gmail_message_id` key (`scheduler-error` event only); present on all other event types including `no-recipient` |
| `event_type` | enum | required | `scheduled` / `approved` / `cancelled` / `sent` / `failed` / `no-recipient` / `duplicate-skipped` / `scheduler-error` / `recovered` |
| `timestamp` | ISO-8601 UTC string | required | When the event occurred |
| `actor` | enum | required | `"operator"` (approve/cancel) or `"system"` (all automated events including `recovered`) |
| `recipient_email` | string or null | optional | Present on all events except `no-recipient` and `scheduler-error` |
| `error_detail` | string or null | optional | Error message; present on `failed` and `scheduler-error` events |
| `retry_count` | integer or null | optional | Present on `failed` events |

---

## Interface Contracts

### REST Endpoints (added to `openclaw_gateway` in 005/006)

**Approve a scheduled email**

```
POST /api/emails/{email_id}/approve
Content-Type: application/json
Body: {} (empty — no request body required)

200 OK
{ "id": "<uuid>", "status": "approved", "approved_at": "<ISO-8601 UTC>" }

404 Not Found
{ "error": "not_found", "email_id": "<uuid>" }

409 Conflict  (email in terminal state: sent / cancelled / failed)
{ "error": "invalid_transition", "email_id": "<uuid>", "current_status": "<status>", "requested": "approve" }

500 Internal Server Error  (email_queue.json write failed — disk full, permissions error)
{ "error": "state_write_failed", "detail": "<message>" }
Note: on 500, no state change is persisted; in-memory state is rolled back to pre-request value.
```

**Cancel a scheduled email**

```
POST /api/emails/{email_id}/cancel
Content-Type: application/json
Body: {} (empty)

200 OK
{ "id": "<uuid>", "status": "cancelled", "cancelled_at": "<ISO-8601 UTC>" }

404 Not Found
{ "error": "not_found", "email_id": "<uuid>" }

409 Conflict  (email already sent — cannot cancel after dispatch; "failed" emails MAY be cancelled, returning 200)
{ "error": "invalid_transition", "email_id": "<uuid>", "current_status": "sent", "requested": "cancel" }

500 Internal Server Error  (email_queue.json write failed)
{ "error": "state_write_failed", "detail": "<message>" }
Note: on 500, no state change is persisted; in-memory state is rolled back.
```

**Idempotency rule**: Calling `/approve` on an already-approved email returns `200` with the current record. Calling `/cancel` on an already-cancelled email returns `200` with the current record. These are not errors.

**Get email queue** (read — for dashboard panel)

```
GET /api/emails?status=scheduled|approved|sent|cancelled|failed|all&limit=50&offset=0

Query parameters:
  status  — one of the enum values above; defaults to "all" if omitted;
            if present but not one of the six valid values → 400 Bad Request
  limit   — max records to return; default 50, max 200; if limit > 200 it is
            silently clamped to 200 (no error)
  offset  — zero-based pagination offset; default 0; if offset ≥ total, returns empty emails array

200 OK
{
  "emails": [ <ScheduledEmail>, ... ],   // sorted by created_at descending
  "total": <integer>,                    // count of records matching the applied status filter (filtered total — e.g., if status=scheduled, total reflects only scheduled entries, not the full queue size)
  "offset": <integer>
}

400 Bad Request  (invalid status value)
{ "error": "invalid_status", "valid_values": ["scheduled","approved","sent","cancelled","failed","all"] }

500 Internal Server Error  (email_queue.json unreadable)
{ "error": "queue_read_failed", "detail": "<message>" }
```

**Get audit log** (read — for dashboard history panel)

```
GET /api/email-events?limit=100&offset=0

Query parameters:
  limit   — max events to return; default 100, max 500; if limit > 500 it is
            silently clamped to 500 (no error)
  offset  — zero-based pagination offset; default 0; if offset ≥ total, returns empty events array

200 OK
{
  "events": [ <EmailEvent>, ... ],       // sorted by timestamp descending
  "total": <integer>,                    // total count of all events in the audit log (unfiltered — no status or event_type filter parameter exists for this endpoint; pagination via limit/offset applies to this total)
  "offset": <integer>
}

500 Internal Server Error  (email_audit.log unreadable or corrupted)
{ "error": "audit_read_failed", "detail": "<message>" }
```

### Orchestrator Integration Contract (004 → 007)

At the end of a **successful** step 3 — i.e., only when the deal has reached `discord-notified` status — `pipeline_orchestrator.runner.run_cycle()` calls:

```
email_scheduler.schedule_for_deal(deal_payload)
```

Where `deal_payload` is a dict containing at minimum these fields sourced from the step-1 result:

| Field | Type | Source |
|---|---|---|
| `gmail_message_id` | string | `result1["deals_extracted"][n]["message_id"]` |
| `sender_email` | string or None | `result1["deals_extracted"][n]["sender_email"]` |
| `sender_name` | string or None | `result1["deals_extracted"][n]["sender_name"]` |
| `subject` | string or None | `result1["deals_extracted"][n]["subject"]` |
| `company_name` | string or None | `result1["deals_extracted"][n]["company_name"]` |
| `deal_summary` | string or None | `result1["deals_extracted"][n]["summary"]` |

`schedule_for_deal()` MUST return a dict with `{"status": "scheduled" | "skipped" | "error", "reason": str}` and MUST NOT raise — exceptions are caught internally, the `scheduler-error` audit event is written, and the error is returned as `{"status": "error", "reason": "<message>"}`.

Concrete `reason` values:

| `status` | `reason` example | When used |
|---|---|---|
| `"scheduled"` | `""` (empty string) | Deal queued successfully |
| `"skipped"` | `"duplicate"` | `gmail_message_id` already has a scheduled/approved/sent entry |
| `"skipped"` | `"no_recipient"` | `sender_email` absent or invalid; `no-recipient` audit event written |
| `"error"` | `"queue_write_failed: [Errno 28] No space left on device"` | Internal exception; `scheduler-error` audit event written before return |

### Step 4b — Dispatch Sub-call (004 → 007)

After all step-4a calls complete for the current cycle, `run_cycle()` calls:

```
email_scheduler.dispatch_pending()
```

This function evaluates all entries in `email_queue.json` with `status: "approved"`, checks the UK business-hours gate and `retry_after` constraint for each, and dispatches eligible emails via SMTP.

| Item | Contract |
|---|---|
| **Arguments** | None |
| **Return** | `{"dispatched": int, "skipped": int, "failed": int}` — counts for the current cycle's dispatch pass (see Counter definitions below) |
| **Raises** | MUST NOT raise — all internal exceptions are caught, logged to `pipeline.log`, and recorded as `scheduler-error` audit events before returning |
| **Call order** | Step 4a: `schedule_for_deal(deal_payload)` is called once per newly processed deal in the current cycle; Step 4b: `dispatch_pending()` is called once per cycle after all step-4a calls complete, regardless of how many deals were processed (including zero) |

**Counter definitions** (per dispatch pass):
- `dispatched` — count of `"approved"` entries whose SMTP send succeeded this cycle; these entries transition to `status: "sent"`.
- `skipped` — count of `"approved"` entries evaluated but not attempted this cycle because either the UK business-hours gate was not open or `retry_after` had not elapsed; these entries remain in `status: "approved"` unchanged.
- `failed` — count of `"approved"` entries that received a send attempt this cycle and failed; includes both emails that incremented `retry_count` but remain in `"approved"` state (retries not yet exhausted) AND emails that exhausted all three retries and transitioned to terminal `status: "failed"`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every fully-processed deal (with a valid `sender_email`) produces a `"scheduled"` entry in `email_queue.json` within 60 seconds of step 3 completing — measurable by comparing `created_at` to the step-3 completion timestamp in `pipeline.log`.
- **SC-002**: Zero emails are delivered via SMTP without a prior `approved` audit event for that `email_id` — verifiable by cross-referencing `sent` events against `approved` events in `email_audit.log` for every `email_id`.
- **SC-003**: 100% of dispatched emails have a `sent_at` UTC timestamp that falls within Mon–Fri 09:00–17:00 Europe/London — verifiable by converting `sent_at` to Europe/London and checking against the weekday and hour.
- **SC-004**: Operator can open the dashboard, read a pending email's full content, approve or cancel it, and see the updated status within 3 clicks and under 5 seconds.
- **SC-005**: All 321 existing unit tests pass after implementation with zero modifications to existing test files.
- **SC-006**: Every email lifecycle event (`scheduled`, `approved`, `sent`, `cancelled`, `failed`, `no-recipient`) appears in `email_audit.log` within 5 seconds of the event occurring.
- **SC-007**: The dashboard email panel and history panel each load within 3 seconds under normal operating conditions.
- **SC-008**: No email send attempt raises an unhandled exception that reaches the gateway process level — all failures are caught, logged to `pipeline.log`, and recorded as `failed` or `scheduler-error` audit events.

---

## Constraints

- **Zero external cost**: Email delivery via Gmail SMTP using existing OAuth2 credentials only. No SendGrid, Mailgun, Postmark, or any paid or third-party email service.
- **Gmail free-tier daily send cap**: Gmail free accounts are limited to 500 outgoing emails per day to external recipients. This feature is designed for low-volume B2B deal outreach and is not expected to approach this limit; however, rate-limit errors from Gmail are handled as retriable failures (FR-010).
- **No new external services**: All state is file-based (`email_queue.json`, `email_audit.log`) alongside existing files. No new databases, message queues, or cloud services.
- **Operator approval mandatory**: No email may be dispatched without a recorded `approved` audit event. This constraint cannot be bypassed or relaxed in v1.
- **Existing tests green**: All 321 passing unit tests remain passing. Existing tests may not be modified or removed.
- **Single recipient per email**: Each scheduled email targets exactly one recipient. Multi-recipient campaigns are out of scope.
- **Fixed template in v1**: Email template content is defined in configuration. No UI for creating, selecting, or editing templates.
- **Process resilience**: Unhandled exceptions in the email scheduler must not terminate the `openclaw_gateway` process (FR-017 / Constitution Gate 6).

---

## Out of Scope

- AI-generated or dynamically composed email content (planned for a future feature)
- Multi-recipient campaigns or bulk send
- Email template management UI
- Unsubscribe / opt-out / GDPR suppression list handling
- Email open-rate or click-rate tracking
- Bounce and delivery receipt processing
- UK bank holiday awareness in the send-time scheduler
- Scheduling outreach to contacts not discovered through the deal pipeline
- Dashboard push notifications when a new email enters the queue

---

## Assumptions

- **File paths for new state files**: `email_queue.json` and `email_audit.log` are written to the same directory as `processed_ids.json` (the directory resolved from `STATE_STORE_PATH`). Optionally, `EMAIL_QUEUE_PATH` and `EMAIL_AUDIT_LOG_PATH` environment variables may be provided as overrides; if unset, the default paths are `<STATE_STORE_PATH directory>/email_queue.json` and `<STATE_STORE_PATH directory>/email_audit.log` respectively. The planner must include these variables in the env var table alongside the existing orchestrator variables.
- The deal contact's email address is the `sender_email` from the original Gmail message captured during 001-gmail-intake and available in the step-1 result dict.
- Outgoing email is sent FROM the same Gmail address used for intake. The operator's Gmail address is the sender.
- **OAuth scope (setup, not runtime)**: Gmail OAuth2 credentials require the `https://mail.google.com/` SMTP send scope. This is a one-time setup step performed by the operator before deploying this feature — it is not a runtime action and does not affect the headless/unattended operation of the pipeline after setup. Once the refreshed `token.json` is in place, no browser interaction is required.
- UK bank holidays are treated as working days in v1.
- The email scheduling step (step 4) and the send dispatcher run inside the existing `openclaw_gateway` process. No new daemon or systemd unit is required. **Concurrency model**: the send dispatcher executes as part of the existing synchronous `run_cycle()` call (step 4 is a new synchronous step), which already runs in a thread pool via `run_in_executor`; HTTP handlers (`POST /api/emails/{id}/approve`, `POST /api/emails/{id}/cancel`) run as asyncio coroutines in the gateway event loop. Because the scheduler thread and the HTTP handler coroutines can concurrently write to `email_queue.json`, all write operations to `email_queue.json` MUST be serialized using a shared in-memory `threading.Lock` instance. This locking requirement applies to both the scheduler path and the HTTP handler path.
- "Operator" is one person with access to the dashboard. There is no multi-user access control. In the audit log, human-triggered events use `actor: "operator"` (a fixed string, not a logged-in identity); automated events use `actor: "system"`.
- **Constitution alignment note — Principle III ("no runtime approval")**: The operator approval gate (US2 / FR-002) is not a pause inside the automated pipeline. The automated pipeline (steps 1–4a) runs to completion and creates a `"scheduled"` entry; the pipeline cycle then ends. Operator approval happens asynchronously via the dashboard at any later time. The automated dispatch sub-step (step 4b / `dispatch_pending()`) is a separate invocation that processes only already-approved entries. No pipeline cycle ever waits for or is blocked by operator input — Principle III is fully satisfied.
- `proposed_send_at` is computed at scheduling time (step 4 of the pipeline cycle) as the estimated next UK business window from that moment. If step 4 runs while Europe/London time is already inside a Mon–Fri 09:00–17:00 window, `proposed_send_at` is set to the current UTC timestamp (dispatch is eligible immediately at the next scheduler tick). When the operator approves, the system recomputes the actual dispatch window from `approved_at`. The `proposed_send_at` field is advisory and is shown in the dashboard for operator reference; actual dispatch time is determined at approval.
- The send dispatcher runs as part of the existing 15-minute pipeline cycle scheduler. Dispatch latency is therefore up to 15 minutes after the business-hours window opens or after operator approval (whichever is later). "Dispatch within business hours" means the `sent_at` timestamp falls within the window, not that dispatch is instantaneous.

---

## Dependencies

- **001-gmail-intake**: Provides `sender_email`, `sender_name`, `subject`, `company_name`, and `deal_summary` fields in the step-1 result, which the email scheduler uses to populate the recipient and template.
- **004-pipeline-orchestrator**: Modified to call `email_scheduler.schedule_for_deal(deal_payload)` as step 4 after step 3 (discord-notify) completes. Responsible for catching any exception returned by the scheduler and logging it without terminating the cycle.
- **005/006-openclaw-gateway + web-dashboard**: Extended with four new REST endpoints (`POST /api/emails/{id}/approve`, `POST /api/emails/{id}/cancel`, `GET /api/emails`, `GET /api/email-events`) and two new dashboard panels (email queue, audit history).
- **Gmail OAuth credentials** (`credentials.json` + `token.json`): Must include the `https://mail.google.com/` SMTP send scope. The operator performs a one-time scope upgrade and re-authorisation before deploying this feature. After that, the system operates fully headlessly with no further browser interaction.
