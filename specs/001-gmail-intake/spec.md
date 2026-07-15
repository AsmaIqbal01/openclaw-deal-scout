# Feature Specification: Gmail Intake & Deal Detection

**Feature Branch**: `001-gmail-intake`
**Created**: 2026-07-09
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Unattended Deal Detection from Inbox (Priority: P1)

The operator's inbox receives a mix of genuine business deal emails (leads,
inquiries, partnership offers targeting UK micro-businesses) and noise (spam,
newsletters, personal emails). The operator wants the system to check the inbox
automatically — with no human present — classify every new email, and produce
a structured record for every genuine deal, while silently discarding non-deals.

**Why this priority**: This is the entire value of the module. Without reliable,
unattended deal detection nothing downstream has any input to work with. All
other stories depend on this one succeeding first.

**Independent Test**: Seed a test inbox with a known mix of N emails (K deals,
N−K non-deals). Invoke `check_new_deals`. Verify: exactly K structured deal
records are produced, N−K emails are logged as skipped, all N message IDs are
recorded in the state store, and no human action is required during the run.

**Acceptance Scenarios**:

1. **Given** an inbox with 3 unread deal emails and 2 unread non-deal emails,
   **When** `check_new_deals` is invoked, **Then** 3 deal records are produced,
   2 emails are logged as "not a deal — skipped", and zero errors are raised.

2. **Given** an inbox with zero unread emails, **When** `check_new_deals` is
   invoked, **Then** the tool returns a success result with zero deal records
   and no error is raised.

3. **Given** the operator's process restarts mid-run (partial state), **When**
   `check_new_deals` is invoked again, **Then** already-processed message IDs
   are skipped and only genuinely unprocessed emails are evaluated.

---

### User Story 2 — Structured Deal Data Extraction (Priority: P2)

For every email classified as a deal, the operator needs a clean, structured
record they can hand off to the CRM-logging step without further manual parsing.
The record must capture sender identity, timing, a human-readable summary, a
category label, and a confidence score — all with defined types and validation.

**Why this priority**: A deal classification alone (yes/no) has no downstream
value. The structured record is what the CRM and notification steps consume. It
must be complete and valid before leaving this module.

**Independent Test**: Send a known deal email to the test inbox. Invoke
`check_new_deals`. Verify the returned record contains all required fields with
correct types, the summary is 1–2 sentences, the category is one of the defined
enum values, the confidence score is between 0 and 1, and the excerpt does not
exceed 500 characters.

**Acceptance Scenarios**:

1. **Given** a deal email with a clear sender, subject, and body, **When**
   `check_new_deals` processes it, **Then** the returned record contains all
   nine DealPayload fields, all required fields are non-empty, all types match
   the DealPayload contract, and no schema validation error is raised.

2. **Given** a deal email whose AI-generated output is missing a required field,
   **When** the tool processes it, **Then** the email is logged as "schema
   validation failed — skipped" and no partial record is returned; the message
   ID is still recorded as processed so it is not retried endlessly.

3. **Given** an email with a body exceeding 8,000 characters, **When**
   `check_new_deals` processes it, **Then** only the first 8,000 characters are
   used for classification; the body beyond that limit is discarded and never
   stored.

4. **Given** an email whose Gmail `internalDate` field is absent, zero, or
   non-numeric, **When** `check_new_deals` processes it, **Then** the message
   is logged at WARN as "invalid metadata — skipped", the message ID is written
   to the state store with outcome `invalid_metadata`, no DealPayload is
   produced, and the tool does not substitute the current UTC time as a
   fallback `received_at`.

---

### User Story 3 — Idempotent Re-runs (Priority: P3)

Polling tools can be invoked multiple times — by retries, by process restarts,
by manual re-runs during debugging. The operator requires that no email ever
produces a duplicate deal record or a duplicate state entry, regardless of how
many times the tool is called.

**Why this priority**: Duplicate CRM entries and duplicate notifications are the
most visible failure mode for an operator. Idempotency is required before this
module is trusted in production, but it depends on P1 and P2 working first.

**Independent Test**: Invoke `check_new_deals` twice on the same inbox without
clearing the state store. Verify the second invocation produces zero deal
records and zero new state entries for message IDs already recorded.

**Acceptance Scenarios**:

1. **Given** the state store contains message ID X, **When** `check_new_deals`
   encounters message ID X in the inbox, **Then** it is skipped without
   classification, with a DEBUG-level log entry, and no duplicate record is
   produced.

2. **Given** a state store entry for message ID X was written but the deal
   record was never completed (partial-write crash recovery), **When**
   `check_new_deals` is invoked, **Then** the message is treated as already
   processed and skipped — no re-classification attempt.

---

### Edge Cases

- **Duplicate message ID in same poll run**: Same ID fetched twice (e.g. due
  to a label change triggering a re-fetch). The second occurrence is silently
  skipped after the first is recorded in the same run.
- **Attachment-only / empty body email**: Logged as "body absent — skipped".
  No classification attempted. Message ID recorded as processed with outcome
  `body_absent`.
- **Non-English email**: Passed to the classifier unchanged. The universal
  confidence floor (see FR-005) applies equally — if `confidence_score` is
  below 0.5 the email is treated as "not a deal" regardless of language.
- **Body longer than 8,000 characters**: Only the first 8,000 characters are
  passed for classification and used as the excerpt source. Content beyond that
  is discarded for this step.
- **Multiple deal signals in one email**: Each individual email message is
  evaluated by its own message ID. Thread grouping is out of scope.
- **Gmail auth token expiry at runtime**: Programmatic token refresh is
  attempted once. If refresh succeeds, polling continues. If it fails, polling
  is suspended and a persistent ERROR log entry is written. The process does
  not crash.
- **Classifier returns non-JSON or malformed output**: Logged as "classification
  output invalid — skipped". Message ID recorded as processed with outcome
  `schema_error` to prevent retry loops.
- **Gmail `internalDate` absent, zero, or non-numeric**: The message is treated
  as un-processable. Logged as "invalid metadata — skipped" at WARN level.
  Message ID recorded as processed with outcome `invalid_metadata`. No
  fallback to current UTC time — a fabricated timestamp would corrupt the
  CRM record downstream.
- **Absent or invalid `From` header** (missing, empty, or containing no `@`):
  The message is treated as un-processable. Logged as "invalid metadata —
  missing sender" at WARN level. Message ID recorded with outcome
  `invalid_metadata`. No classification attempted. This prevents a DealPayload
  with a null or invalid required `sender_email` field from reaching downstream
  steps.
- **Absent or empty `Subject` header**: The message is treated as
  un-processable. Logged as "invalid metadata — missing subject" at WARN level.
  Message ID recorded with outcome `invalid_metadata`. No classification
  attempted.

---

## Requirements *(mandatory)*

### Functional Requirements

**Gmail Polling**

- **FR-001**: The system MUST expose a callable tool named `check_new_deals`
  that an orchestrating agent can invoke on demand.
- **FR-002**: `check_new_deals` MUST retrieve all unread messages received
  since the timestamp of the last successful poll (persisted in the state
  store), using pre-authorised inbox credentials — with no interactive login
  step required at runtime, ever. On the first-ever invocation (state store
  absent or empty), the system MUST default to a 24-hour lookback window,
  retrieving messages received in the 24 hours prior to invocation time.
- **FR-003**: If no new messages are found, the tool MUST return a success
  result with zero deal records and write one INFO-level "inbox empty" log
  entry. This is a normal, non-error condition.
- **FR-003a**: Each poll cycle MUST process at most 50 messages. "Oldest" is
  defined as smallest `internalDate` (Unix epoch ms) ascending. The 50-message
  cap is applied to the full set of unread messages returned by the Gmail API
  for the poll window, sorted by `internalDate` ascending, BEFORE the
  already-processed-ID filter is applied. Messages in the fetched 50 that are
  already in the state store are excluded from `processed_count` and
  `skipped_count` per the Tool Contract definition (they are pre-filter skips).
  Unselected messages beyond the 50 are left unread and picked up in subsequent
  poll cycles. The limit MUST be configurable via the environment variable
  `MAX_MESSAGES_PER_POLL` (default: `50`).
- **FR-003b**: `check_new_deals` is designed for single-instance invocation.
  Concurrent invocations against the same `STATE_STORE_PATH` are not
  supported. The tool MUST acquire an exclusive file lock on
  `STATE_STORE_PATH` at startup and release it on exit. If the lock cannot
  be acquired (another invocation is running), the tool MUST log WARN
  "concurrent invocation detected — aborting" and return immediately with
  `status: "error"` and `error_details: "concurrent invocation"` without
  processing any messages.

**Deal Classification**

- **FR-004**: For each new email the system MUST determine, using a defined
  classification prompt and response schema, whether the email represents a
  genuine business deal opportunity relevant to UK micro-businesses (fewer than
  10 employees).
- **FR-005**: The classification MUST produce a boolean `is_deal` flag and a
  `confidence_score` (float, 0.0–1.0). An email is treated as "not a deal"
  if `is_deal` is false OR if `confidence_score` is below 0.5, regardless of
  language. Emails treated as "not a deal" MUST be logged at INFO level and
  not passed further.
- **FR-006**: The classification prompt and expected JSON response schema MUST
  be defined in the feature plan and version-controlled. The prompt MUST
  instruct the classifier to respond in structured JSON only, not free prose.
- **FR-007**: If the classifier returns a rate-limit error, the system MUST
  retry with exponential back-off: 1 initial attempt + 3 retries = 4 total
  attempts. Wait 10 s before retry 1; wait 30 s before retry 2; wait 60 s
  before retry 3. If retry 3 fails, the email is logged as "classification
  rate-limited — skipped" at WARN level and its message ID recorded as
  processed with outcome `rate_limited`. This aligns with Constitution
  Principle VI ("max 3 retries, 60 s cap").

**DealPayload Extraction**

- **FR-008**: For each email classified as a deal, the system MUST produce one
  DealPayload record conforming exactly to the contract in Key Entities below.
- **FR-009**: If the classifier output is missing any required DealPayload
  field, or any field fails its validation rule, the email MUST be logged as
  "schema validation failed — skipped" at WARN level. Its message ID MUST be
  recorded as processed with outcome `schema_error`. No partial record is
  returned.
- **FR-010**: The `raw_email_excerpt` field MUST be capped at 500 characters,
  truncated at the nearest word boundary at or before that limit. If the body
  is shorter than 500 characters, the full body is used. If body is absent,
  the field is null.
- **FR-011**: The `deal_summary` MUST be 1–2 sentences. A sentence boundary
  is defined as a period, exclamation mark, or question mark followed by a
  space or end-of-string (abbreviation periods mid-word, e.g. "U.K.", do not
  count as sentence boundaries). If the classifier returns more than 2
  sentences, the field is truncated after the second sentence boundary. The
  500-character limit in the DealPayload contract is then applied as a hard
  cap: if the 2-sentence result still exceeds 500 characters, it is further
  truncated at the nearest word boundary at or before 500 characters. The
  sentence rule is applied first; the character cap is the final hard
  constraint.

**Idempotency & State Store**

- **FR-012**: The system MUST maintain a persistent state store keyed by
  `gmail_message_id`. The store MUST survive process restarts without data
  loss.
- **FR-013**: Each message ID MUST be written to the state store before the
  tool returns a result for that message. If the process crashes after the
  write but before returning, the message is treated as processed on the next
  invocation.
- **FR-014**: On each invocation, the system MUST read the full state store
  before polling and skip any message whose ID is already present.
- **FR-015**: The state store MUST use a file-based mechanism with zero
  infrastructure cost. The store file path MUST be configurable via the
  environment variable `STATE_STORE_PATH`, defaulting to
  `./data/processed_ids.json` if the variable is absent.

**Error Handling**

- **FR-016**: Gmail credential failure or token expiry: attempt programmatic
  token refresh once. On success, continue polling. On failure, log ERROR,
  return `status: "error"` for the current invocation, and suspend polling
  for the current invocation only — the next invocation will attempt the
  full cycle again (including another token refresh attempt). Suspension does
  not persist across invocations.
- **FR-017**: Gmail rate limit or quota exhaustion: log WARN with quota-reset
  time if available; suspend polling for the current cycle. No crash.
- **FR-018**: Malformed or empty email body: log INFO "body absent or malformed
  — skipped"; record message ID with outcome `body_absent`; skip classification.
- **FR-019**: Network failure mid-poll: log WARN; abort the current poll cycle
  cleanly; do not partially update the state store for messages not yet fully
  processed.
- **FR-021**: Any Gemini API error that is not an HTTP 429 rate-limit response
  (including HTTP 400, 500, 503, connection refused, and request timeout) MUST
  be handled at the per-message level: log WARN "classification failed:
  [HTTP status / error type]", record the message ID in the state store with
  outcome `classification_error`, and continue processing the next message.
  No retry is attempted for non-429 Gemini errors (to avoid burning quota on
  a server-side error). The `classification_error` outcome prevents the same
  email from being re-evaluated on subsequent poll cycles.
- **FR-020**: Any unhandled exception within the tool boundary MUST be caught
  at the per-message processing level. The exception MUST be logged as ERROR
  with full stack trace. The in-progress message ID MUST be written to the
  state store with outcome `classification_error` before the exception handler
  returns, so the message is not re-evaluated on subsequent runs. Processing
  then continues with the next message; the overall run does NOT abort on a
  per-message unhandled exception. The exception MUST NOT propagate to crash
  the calling agent process. Only a cycle-level failure (credential failure,
  network failure, state store read failure) sets `status: "error"` and aborts
  the run.

### Key Entities

**DealPayload** — the structured output produced for each confirmed deal:

| Field | Type | Required | Source | Validation rules |
|---|---|---|---|---|
| `gmail_message_id` | string | Yes | Gmail API (`id` field) | Non-empty; unique per run; used as idempotency key |
| `sender_email` | string | Yes | Gmail API (`From` header address) | Non-empty; must contain `@` |
| `sender_name` | string | No | Gmail API (`From` header display name) | null if absent from header |
| `subject` | string | Yes | Gmail API (`Subject` header) | Non-empty |
| `received_at` | string | Yes | Gmail API (`internalDate` field, converted from Unix epoch ms to ISO 8601 UTC) | Format `YYYY-MM-DDTHH:MM:SSZ` |
| `deal_summary` | string | Yes | Classifier output | 1–2 sentences; non-empty; max 500 characters |
| `deal_category` | enum | Yes | Classifier output | One of: `lead`, `partnership_inquiry`, `vendor_offer`, `rfq`, `other` |
| `confidence_score` | float | Yes | Classifier output | 0.0–1.0 inclusive |
| `raw_email_excerpt` | string | No | Classifier output | Max 500 characters; null if body absent |

The first five fields are populated from the Gmail API response before the
classifier is called. The final four fields are populated from the classifier
JSON response. `received_at` uses Gmail's `internalDate` (server receipt time)
rather than the RFC 822 `Date` header (sender-reported time) to ensure a
reliable, unforged timestamp.

**ProcessedMessage** — one entry per email seen by the tool, written to the state store:

| Field | Type | Notes |
|---|---|---|
| `gmail_message_id` | string | Primary key |
| `processed_at` | string | ISO 8601 UTC timestamp recorded at the moment the atomic state store write completes for this entry |
| `outcome` | enum | One of: `deal_extracted`, `not_a_deal`, `schema_error`, `rate_limited`, `body_absent`, `invalid_metadata`, `classification_error` |

Note: `auth_failure` is a cycle-level event, not a per-message event. Auth failure
halts the poll cycle before any individual message is fetched or evaluated; no
message ID is ever recorded with an auth-failure outcome. It is absent from this
enum by design and handled exclusively at the cycle level in FR-016.

**State Store Schema** — the exact top-level structure of `processed_ids.json`:

```json
{
  "last_poll_time": "ISO-8601 UTC string | null",
  "messages": [ ProcessedMessage, ... ]
}
```

Rules governing this structure:

- `last_poll_time` is `null` on a freshly created file (no prior successful
  poll). A `null` value triggers the 24-hour lookback window defined in
  FR-002.
- `last_poll_time` is updated to the current UTC time only after a poll
  cycle completes without a fatal error (credential failure or network
  failure that prevents any messages from being fetched). Per-email errors
  (schema error, rate limit, body absent) do NOT block the timestamp update.
- If `last_poll_time` is present but is not a valid ISO 8601 string (file
  corruption), the system MUST treat it as `null`, log WARN
  "state store: last_poll_time malformed — defaulting to 24-hour window",
  and continue. This is never a fatal startup error.
- Each ProcessedMessage entry is appended to the `messages` array
  individually and written atomically (write to a temp file, then rename)
  before the tool moves to the next email. A crash between writes leaves
  only the successfully renamed entries; unwritten entries are re-evaluated
  on the next run.
- If the state store file cannot be written (disk full, permission denied),
  the system MUST log ERROR "state store write failed: [reason]", skip
  recording the current message ID, and continue processing remaining
  emails. The affected message ID will be re-evaluated on the next run
  (acceptable duplication risk — logged at WARN on re-encounter).
- On FR-017 (Gmail rate limit mid-cycle): all ProcessedMessage entries
  already committed before polling suspended are retained. No rollback.
  The partially updated `messages` array is the valid state for the next
  run. A Gmail rate limit is treated as a fatal event for `last_poll_time`
  update purposes: the timestamp is NOT advanced for the rate-limited cycle.
  This ensures the next poll re-covers the full window from the previous
  successful poll, preventing unfetched messages from falling outside the
  next poll window permanently.
- **Size management (MVP)**: The `messages` array grows by one entry per
  email evaluated and is unbounded for MVP. Size management and archival are
  explicitly deferred to a future spec. For planning purposes, assume a
  long-running service producing ~50 emails/day yields ~18 000 entries/year,
  each entry approximately 150 bytes — approximately 2.7 MB/year. This is
  within acceptable disk bounds for MVP without archival. If `STATE_STORE_PATH`
  disk usage exceeds 50 MB, the system MUST log WARN
  "state store exceeding 50 MB — archival recommended" once per poll cycle.
- On state store read failure at startup (file exists but cannot be read —
  permission denied, file locked by another process, or content is not valid
  JSON at the top level): the system MUST log ERROR
  "state store unreadable: [reason] — polling suspended" and suspend the
  poll cycle without processing any messages. This is treated as a fatal
  startup error. Treating a corrupt state store as fresh state would risk
  reprocessing already-logged deals, violating Principle IV; therefore
  silent fallback to fresh state is prohibited for read failures. The
  operator must resolve the file issue before the next invocation.
  (Contrast: a missing file is not an error — it is the normal first-run
  state, handled by the 24-hour lookback window in FR-002.)

**ClassificationRequest** — the inputs passed to the AI classifier per email:

| Field | Type | Notes |
|---|---|---|
| `subject` | string | Email subject line |
| `sender_email` | string | Sender address |
| `sender_name` | string \| null | Sender name if available; null otherwise |
| `body_excerpt` | string \| null | Email body, capped at 8,000 characters; null if body absent |
| `target_segment` | string | Fixed value: `"UK micro-business, fewer than 10 employees"` |

The classifier MUST return a JSON object containing: `is_deal` (boolean),
`confidence_score` (float), `deal_category` (enum), `deal_summary` (string),
`raw_email_excerpt` (string). The exact prompt text is defined in the plan.

### Tool Contract

**`check_new_deals`** — zero input parameters. All runtime context is read
from environment variables and the state store (last-poll timestamp). The
calling agent passes no arguments.

Required environment variables:

| Variable | Default | Behaviour if absent |
|---|---|---|
| `GMAIL_CREDENTIALS_PATH` | none | Fatal startup error — log ERROR, suspend polling |
| `STATE_STORE_PATH` | `./data/processed_ids.json` | Use default path |
| `MAX_MESSAGES_PER_POLL` | `50` | Use default limit |

**Return type**:

```
{
  status:          "ok" | "error",
  deals_extracted: DealPayload[],
  processed_count: number,          // emails fetched from Gmail this run (excludes already-seen pre-filter skips)
  skipped_count:   number,          // non-deals + per-email errors (excludes already-seen pre-filter skips)
  error_details:   string | null    // populated only when status is "error"
}
```

- `status` is `"error"` only when the entire poll cycle cannot complete
  (e.g. credential failure, network failure, state store read failure).
  Individual per-email failures (schema error, rate limit, body absent,
  invalid metadata) do NOT set `status` to `"error"` — they increment
  `skipped_count` and the run continues.
- `deals_extracted` is always an array; it is empty `[]` when no deals are
  found, never null.
- On a normal empty-inbox run: `status: "ok"`, `deals_extracted: []`,
  `processed_count: 0`, `skipped_count: 0`, `error_details: null`.
- On a fatal-error return (`status: "error"`): `deals_extracted` is always
  `[]` regardless of how many deals were extracted before the failure point;
  `processed_count` and `skipped_count` reflect counts accumulated before
  the failure (useful for diagnostics); `error_details` is a single
  human-readable string containing the top-level error message only — no
  stack trace (the full stack trace is written to the error log per FR-020).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a test inbox with N unread emails (mix of deal and
  non-deal), the tool identifies all deal emails with zero crashes, completing
  the full run without operator intervention.
- **SC-002**: All N processed message IDs are present in the state store after
  a single run. A second run on the same unchanged inbox produces zero new deal
  records and zero new state entries.
- **SC-003**: Every DealPayload returned by a run passes all validation rules
  in the Key Entities table — no required field is null, no enum value is
  outside the defined set, no confidence score is outside 0.0–1.0.
- **SC-004**: Each of the thirteen defined boundary conditions can be triggered
  in isolation in a test environment; in every case the tool returns without
  crashing, writes the correct log entry at the correct severity level, and
  leaves the state store in the expected state:
  (1) credential failure, (2) Gmail rate limit, (3) classifier 429 rate limit,
  (4) classifier non-429 error (e.g. 500), (5) schema validation failure,
  (6) invalid metadata (absent/malformed internalDate), (7) missing required
  header (absent From or Subject), (8) malformed/empty body, (9) network
  failure mid-poll, (10) unhandled per-message exception, (11) state store
  read failure, (12) state store write failure, (13) concurrent invocation.
  Note: empty inbox is a normal non-error condition per FR-003 — it is verified
  by SC-001 scenario 2, not listed here as a boundary condition.
- **SC-005**: A run interrupted mid-poll (simulated process kill) followed by
  an immediate re-run produces no duplicate deal records for message IDs
  already written to the state store before the interruption.

---

## Out of Scope

- Creating or updating any CRM record (HubSpot or otherwise)
- Sending any notification (Discord or otherwise)
- Scheduling or orchestration logic (cron, systemd timers) — this spec covers
  the tool itself only, not its invocation schedule
- Multi-account or multi-inbox Gmail support
- Email archiving, labelling, or mutation of the Gmail mailbox in any way
- Processing sent items, drafts, or spam folders
