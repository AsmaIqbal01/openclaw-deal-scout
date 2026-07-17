# Feature Specification: Discord Deal Notification

**Feature Branch**: `003-discord-notification`
**Created**: 2026-07-17
**Status**: Draft

## Overview

When the CRM-logger module marks a deal as `crm-logged`, this feature sends a
structured alert to a configured Discord channel so the operator has near-real-time
visibility into every confirmed deal without checking the CRM manually.

The notifier is a standalone adapter behind a documented contract. Swapping to a
different channel (Slack, email) requires only a single config change and a new
adapter — no changes to deal-detection or CRM-logging logic.

---

## Constitution Check Gates

This spec explicitly addresses all six Constitution Check Gates before proceeding
to planning.

| Gate | Principle | Answer | Evidence |
|------|-----------|--------|---------|
| Does this introduce a paid dependency? | I — Zero Cost | **No** | Discord webhooks are free with no rate-limit that triggers cost; no credit card required |
| Does this add a non-Gmail intake source? | II — Gmail-Only Intake | **No** | This feature is downstream of intake; it reads from the existing state store only |
| Does this require a runtime browser login? | III — Headless | **No** | Discord webhook URL is a static credential stored in `.env`; no OAuth flow |
| Does this risk duplicate notifications? | IV — State-Driven Idempotency | **No** | FR-002, FR-005, and FR-009 mandate idempotency; a deal already `discord-notified` is a no-op |
| Does this modify core pipeline files to add a notifier? | V — Modular Notification Architecture | **No** | Notifier logic lives in a dedicated adapter; active notifier selected via `NOTIFIER` env var |
| Does this allow an exception to crash the agent? | VI — Graceful Degradation | **No** | FR-006, FR-011, and FR-012 define explicit failure modes with retry state; no unhandled crash paths |

All six gates pass. Any future change that flips a gate to "Yes" is a constitution
violation and must be resolved before merge.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Alert Operator When a New Deal Lands (Priority: P1)

The operator checks Discord and sees a rich alert for every confirmed business deal
that was pulled from Gmail and logged to CRM — without logging into HubSpot or
re-reading the inbox. The alert appears automatically within the next notification
cycle after the CRM write completes.

**Why this priority**: This is the terminal output of the entire pipeline.
Without the alert, the operator has no low-friction signal that a deal arrived.
US2–US4 are safety and architecture guarantees that protect this core value.

**Independent Test**: Seed the state store with one entry in `crm-logged` status
containing all nine DealPayload fields. Invoke `notify_discord`. Verify: a Discord
message is delivered to the configured channel, the deal's status transitions to
`discord-notified`, and the state store entry is updated atomically.

**Acceptance Scenarios**:

1. **Given** a state store entry with `status = "crm-logged"` and all DealPayload
   fields present, **When** `notify_discord` runs, **Then** a Discord message is
   delivered to the configured channel within the cycle and the entry is updated
   to `status = "discord-notified"`.

2. **Given** multiple entries with `status = "crm-logged"`, **When** `notify_discord`
   runs, **Then** one Discord message is sent per entry, each is marked
   `discord-notified` after delivery, and failures on any single entry do not
   prevent processing of the others.

3. **Given** the Discord channel has zero existing messages, **When** `notify_discord`
   runs for a confirmed deal, **Then** the alert appears with: sender name and email,
   deal category, confidence score, deal subject, and a one-to-two sentence summary.

---

### User Story 2 — Idempotent Re-run Never Sends Duplicates (Priority: P2)

If `notify_discord` is called again for a deal already marked `discord-notified` —
due to a crash-restart, a manual retry, or a concurrent invocation — no second
Discord message is sent and the state store is not corrupted.

**Why this priority**: Duplicate Discord pings erode operator trust immediately.
This is the same idempotency guarantee that Step 1 (gmail-intake) and Step 2
(crm-logger) both enforce, and it must be present here before any retry or
resilience logic can be safe to add.

**Independent Test**: Set a state store entry to `status = "discord-notified"`.
Call `notify_discord` twice in sequence. Verify: the Discord channel receives
exactly one message (the one already sent before the test), and the state store
entry is unchanged after both calls.

**Acceptance Scenarios**:

1. **Given** a state store entry with `status = "discord-notified"`, **When**
   `notify_discord` is called, **Then** no Discord API call is made and the entry
   status remains `discord-notified`.

2. **Given** an agent restart mid-cycle after some deals are already
   `discord-notified`, **When** the cycle resumes, **Then** only deals still in
   `crm-logged` or `crm-logged-notify-pending` are processed; already-notified
   deals are skipped.

---

### User Story 3 — Retryable Pending State on Discord Failure (Priority: P3)

When a Discord API call fails (network error, rate limit, webhook revoked), the
deal is left in a retryable `crm-logged-notify-pending` state — not silently
dropped, and not falsely marked as notified. On the next notification cycle,
pending deals are drained first before new `crm-logged` deals are attempted.

**Why this priority**: Silent drops are worse than failures because they leave the
operator uninformed about deals that were never alerted. Explicit pending state
enables recovery without Gmail or CRM API calls.

**Independent Test**: Configure the notifier with an invalid webhook URL. Seed the
state store with one `crm-logged` entry. Run `notify_discord`. Verify: the entry
is updated to `crm-logged-notify-pending`, a `[WARN] Notifier failed` log line is
written, and no `discord-notified` marker appears. Then fix the webhook URL and
run `notify_discord` again; verify the pending entry is retried and succeeds.

**Acceptance Scenarios**:

1. **Given** a deal in `crm-logged` state, **When** the Discord API returns a
   network error or 5xx response, **Then** the deal is marked
   `crm-logged-notify-pending`, a WARN log is emitted, and the process continues
   without crashing.

2. **Given** a deal in `crm-logged` state, **When** the Discord API returns HTTP 429
   (rate limit), **Then** the deal is marked `crm-logged-notify-pending`, no retry
   is attempted within the current cycle, and the deal is retried on the next cycle.

3. **Given** deals in both `crm-logged-notify-pending` and `crm-logged` states,
   **When** `notify_discord` runs, **Then** `crm-logged-notify-pending` deals are
   attempted first (drain-first ordering), followed by new `crm-logged` deals.

4. **Given** a Discord API failure, **When** the failure is recorded in the state
   store, **Then** the `error_reason` field captures the failure type and the
   `notified_at` field is absent (not set to a false timestamp).

---

### User Story 4 — Swappable Notifier Contract (Priority: P4)

A future operator who uses Slack instead of Discord can add a `notify_slack`
adapter and activate it via a single environment variable change. No changes to
`gmail_intake`, `crm_logger`, or orchestrator files are required.

**Why this priority**: This is a constitution mandate (Principle V). It bounds
the implementation by preventing tight coupling between notification target and
core pipeline logic. It does not deliver new operator-facing behaviour in the MVP
but governs the architecture of US1–US3.

**Independent Test**: Implement a minimal `notify_noop` adapter that satisfies the
documented notifier contract. Set `NOTIFIER=noop`. Run `notify_discord`. Verify:
the noop adapter is dispatched, no Discord API call is made, and the pipeline
completes without errors. This test proves the contract is real and the adapter is
swappable.

**Acceptance Scenarios**:

1. **Given** `NOTIFIER=discord` in the environment, **When** the notification cycle
   runs, **Then** the Discord adapter is invoked.

2. **Given** `NOTIFIER` is set to any string other than a known adapter name,
   **When** the notification cycle starts, **Then** it fails immediately with a
   descriptive error naming the unrecognised value; no partial state is written.

3. **Given** a new notifier adapter that implements the published contract, **When**
   it is registered and `NOTIFIER` is pointed to it, **Then** it handles deals
   without any changes to `gmail_intake/`, `crm_logger/`, or the orchestrator.

---

### Edge Cases

- **Deal already `discord-notified`**: `notify_discord` is a strict no-op — no
  Discord API call, no state mutation, no log noise beyond a DEBUG trace.
- **Webhook URL absent or empty**: Notifier fails at startup with a descriptive
  `EnvironmentError`; no cycle begins, no state is written.
- **Webhook URL syntactically invalid (not a URL)**: Treated the same as a failed
  API call; deal moves to `crm-logged-notify-pending`.
- **State store file absent or OS-unreadable at cycle start**: Cycle aborts with
  an ERROR log (`[ERROR] State store could not be opened: <reason>`); no
  notification attempts are made; no file is created or overwritten.
- **State store file is OS-readable but contains invalid JSON**: Cycle aborts
  immediately with `[ERROR] State store parse failed: <exception class and message>`.
  No notification attempts are made. The file is NOT overwritten or renamed — the
  operator must inspect and repair it manually. This prevents silent data loss
  from a corrupted state file.
- **All nine DealPayload fields present but `deal_summary` is empty string**:
  Message is still sent; the summary field in the Discord embed renders as
  `(no summary)` rather than an empty block.
- **Discord embeds character limits exceeded** (e.g., `subject` > 256 chars):
  Field is truncated server-side by the adapter before sending; the original value
  in the state store is not modified.
- **`crm-logged-notify-pending` entries with no retry ceiling**: No maximum
  retry count is enforced. A pending entry retries on every subsequent
  notification cycle until the operator resolves the underlying issue (e.g.,
  restores the webhook URL). There is no terminal `notify-failed` state in this
  spec. The state store schema does not require a retry-counter field. This
  decision is explicit: indefinite retry is preferable to silent termination for
  an unattended operator, and an ERROR log on each failed attempt provides the
  escalation signal.
- **Concurrent invocations** of the notification cycle: State store lock
  (same portalocker pattern as Steps 1 and 2) prevents both from writing. The
  second caller acquires the lock, detects the conflict, logs
  `[WARN] Concurrent invocation detected — notification cycle already running`,
  and returns immediately with `status = "error"` and
  `error_details = "concurrent invocation"`. No notification attempts are made
  by the second caller and no state is written.
- **Discord delivery succeeds (HTTP 2xx) but state-store write fails**: The
  delivery has already occurred and cannot be undone. The system MUST log
  `[ERROR] State write failed after successful Discord delivery for <id>`. The
  entry MUST remain in `crm-logged` in the state store (since the write failed),
  which means the deal WILL be retried on the next cycle. The Discord adapter
  MUST be idempotent enough to tolerate a second send attempt — this is an
  acceptable trade-off (at-most-once delivery cannot be guaranteed when the
  state store is the only source of truth).

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST send a formatted alert to the configured Discord
  channel for every deal whose state store entry carries `status = "crm-logged"`.

- **FR-002**: The system MUST be idempotent: calling `notify_discord` on a deal
  already marked `discord-notified` MUST be a no-op — no Discord API call is made
  and the state store entry is not modified.

- **FR-003**: Each Discord alert MUST include, at minimum: the sender's display
  name and email address, the deal category, the confidence score expressed as a
  percentage, the deal subject (truncated if over the channel's character limit),
  and the deal summary.

- **FR-004**: The system MUST update the deal's state store entry to
  `status = "discord-notified"` only AFTER the Discord API confirms the delivery
  (HTTP 2xx response). No optimistic marking.

- **FR-005**: On any Discord API failure (network error, 4xx except 429, 5xx, or
  timeout), the system MUST update the entry to
  `status = "crm-logged-notify-pending"` with an `error_reason` field, emit a
  `[WARN] Notifier failed` log line, and continue processing remaining deals in
  the cycle without crashing.

- **FR-006**: On Discord API HTTP 429, the system MUST apply the same treatment as
  FR-005 (pending state, WARN log) and MUST NOT retry within the current cycle.

- **FR-007**: The notification cycle MUST drain all `crm-logged-notify-pending`
  entries before processing new `crm-logged` entries (drain-first ordering,
  consistent with Step 2's crm-pending drain).

- **FR-008**: The Discord webhook URL MUST be read exclusively from the `DISCORD_WEBHOOK_URL`
  environment variable. It MUST NOT be hard-coded or committed to version control.

- **FR-009**: The active notifier MUST be selected via the `NOTIFIER` environment
  variable. Changing `NOTIFIER` from `discord` to a different value MUST activate
  a different adapter without modifying any file in `gmail_intake/`, `crm_logger/`,
  or the orchestrator.

- **FR-010**: The notifier adapter interface MUST be documented such that
  `notify_slack(deal)` can satisfy the same contract as `notify_discord(deal)`
  without requiring changes to this feature's spec, data model, or state-store
  schema.

- **FR-011**: The notification cycle MUST acquire the same state store lock used
  by Steps 1 and 2, preventing concurrent writes from any pipeline step.

- **FR-012**: The notifier MUST operate without any interactive credential step.
  Discord authentication uses the static webhook URL from `.env` only.

- **FR-013**: An unhandled exception within a single deal's notification attempt
  MUST be caught at the per-deal boundary. The deal MUST be marked
  `crm-logged-notify-pending` and the cycle MUST continue with the next deal.

- **FR-014**: If `NOTIFIER` is absent or set to an unrecognised value, the
  notification cycle MUST abort immediately with a descriptive error before
  reading the state store or making any network call.

- **FR-015**: The Discord HTTP request MUST apply a 10-second timeout. A
  response not received within 10 seconds is treated identically to a network
  error: the deal is marked `crm-logged-notify-pending` with
  `error_reason = "ConnectionError: timed out after 10s"` and a WARN log is
  emitted.

- **FR-016**: If a Discord delivery (HTTP 2xx) is confirmed but the subsequent
  state-store write fails, the system MUST log `[ERROR] State write failed after
  successful Discord delivery for <gmail_message_id>`. The entry remains in its
  pre-write status in the state store, allowing retry on the next cycle.

### Key Entities

- **DiscordNotificationAdapter**: Implements the Notifier contract for Discord.
  Holds the webhook URL. Exposes a single method that accepts a deal record and
  returns a `NotifyOutcome`. Has no knowledge of state-store internals.

- **NotifierContract**: The documented interface all adapters must satisfy.
  Input: a deal record with the nine DealPayload fields. Output: one of
  `"discord-notified"` | `"crm-logged-notify-pending"` | `"skipped"`.
  No side-effects beyond the delivery attempt itself.

- **NotifyOutcome**: The typed result of a single notification attempt.
  Values: `"discord-notified"` (delivered), `"crm-logged-notify-pending"`
  (failed, retryable), `"skipped"` (idempotency no-op).

- **NotificationCycleResult**: Aggregate result returned by the notification
  cycle. Fields: `discord_notified` count, `notify_pending` count,
  `skipped` count, `status` ("ok" | "error"), optional `error_details`.

### Data Contracts

#### DealPayload fields (all nine required at notification time)

These are guaranteed to be present in the state store entry by Step 2's FR-015.
The notifier MUST NOT call any external API to retrieve missing fields.

| Field | Type | Constraint |
|---|---|---|
| `gmail_message_id` | string | Non-empty; idempotency key |
| `sender_email` | string | Non-empty; contains `@` |
| `sender_name` | string or null | Null if absent from Gmail From header |
| `subject` | string | Non-empty; max 255 chars after Step 2 truncation |
| `received_at` | string | ISO 8601 UTC |
| `deal_summary` | string | 1–2 sentences; max 500 chars |
| `deal_category` | string | One of: `lead`, `partnership_inquiry`, `vendor_offer`, `rfq`, `other` |
| `confidence_score` | float | 0.0–1.0 inclusive |
| `raw_email_excerpt` | string or null | Max 500 chars; null if body absent |

#### State store fields written on a successful delivery

When the Discord adapter receives an HTTP 2xx response **and** the subsequent
state-store write succeeds, the entry MUST be updated with:

| Field | Type | Value written |
|---|---|---|
| `status` | string | `"discord-notified"` |
| `notified_at` | string | ISO 8601 UTC timestamp of the moment the HTTP 2xx response was received (same format as `received_at`, e.g. `"2026-07-17T10:23:45.123456Z"`) |

`notified_at` MUST NOT be written when the entry transitions to
`crm-logged-notify-pending`. If a delivery is confirmed (HTTP 2xx) but the
state-store write subsequently fails (FR-016), neither `status` nor `notified_at`
are updated — the entry retains its pre-write value.

#### error_reason field

When a deal transitions to `crm-logged-notify-pending`, the state store entry
MUST include an `error_reason` field with:

- Type: string
- Maximum length: 255 characters
- Minimum content: HTTP status code (if an HTTP response was received) or
  exception class name (if no response), followed by a short message excerpt
- Example values: `"429 Too Many Requests"`, `"ConnectionError: timed out after 10s"`, `"500 Internal Server Error: upstream error"`

#### Discord webhook request contract

The Discord adapter MUST send an HTTP POST request with:

- URL: value of `DISCORD_WEBHOOK_URL` environment variable
- Method: POST
- Content-Type: `application/json`
- Request timeout: **10 seconds** (a response not received within 10 seconds
  is treated as a timeout failure; the deal is marked `crm-logged-notify-pending`)
- Body shape:

```
{
  "embeds": [
    {
      "title": "<subject> (max 256 chars, truncated with '...' if longer)",
      "description": "<deal_summary>",
      "fields": [
        { "name": "From",       "value": "<sender_name> <<sender_email>> when sender_name is non-null; \"<sender_email>\" alone when sender_name is null", "inline": true },
        { "name": "Category",   "value": "<deal_category>",              "inline": true },
        { "name": "Confidence", "value": "<confidence_score × 100>%",   "inline": true }
      ]
    }
  ]
}
```

- `raw_email_excerpt`, `received_at`, and `gmail_message_id` are NOT included
  in the embed body; they remain in the state store only.
- The `color` field is optional and left to the adapter implementation.
- A HTTP 2xx response from Discord constitutes confirmed delivery.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every deal that reaches `crm-logged` state is represented in the
  Discord `#deal_alerts` channel within the next completed notification cycle —
  100% delivery rate under normal operating conditions.

- **SC-002**: Zero duplicate Discord messages are sent for any deal, across any
  number of retries, restarts, or concurrent invocations.

- **SC-003**: A total Discord outage results in zero deal data loss — 100% of
  affected deals remain in `crm-logged-notify-pending` and are retried on the
  next cycle after the outage resolves.

- **SC-004**: A new notifier adapter can be implemented, registered, and activated
  with changes to at most 2 files, neither of which is in `gmail_intake/`,
  `crm_logger/`, or the orchestrator.

- **SC-005**: 100% of Discord API failures (all error types) are written to the
  state store as `crm-logged-notify-pending` within the same notification cycle
  in which the failure occurs — no silent drops.

- **SC-006**: The `notify_discord` call for an already-`discord-notified` deal
  completes in under 10 ms (no network round-trip), confirming the idempotency
  check happens before any API call.

---

## Assumptions

- Discord authentication for the MVP uses a webhook URL (no bot token, no OAuth).
  The webhook URL is treated as a secret and stored in `.env` under
  `DISCORD_WEBHOOK_URL`.
- The target channel is `#deal_alerts` as specified in the constitution's
  Technology Stack table.
- Alert formatting uses Discord's webhook embed format (JSON payload with
  `embeds` field). Color-coding by category is an implementation detail and
  not a functional requirement.
- The notification cycle is triggered by the same orchestrator that runs the CRM
  cycle; no separate scheduling service is introduced.
- All nine DealPayload fields are available in the state store entry at
  notification time (guaranteed by Step 2's FR-015 — no Gmail or CRM API calls
  are needed during notification).
- The `NOTIFIER` environment variable is **required** and has no default. If
  absent or set to an unrecognised value, the notification cycle MUST fail
  immediately with a descriptive `EnvironmentError` before any state is read
  or written. This matches the fail-fast config policy used by Steps 1 and 2.
- Rate-limit retry budget is one cycle (deal stays pending until next scheduled
  run), consistent with the HubSpot rate-limit policy in Step 2.

---

## Out of Scope

- Bot token authentication (webhook-only for MVP)
- Per-category Discord channels (single channel only)
- Slack, email, SMS, or any other notifier adapter implementation (only the
  contract that enables them)
- Notification delivery receipts or read-confirmation tracking
- Operator-controlled notification filters (e.g., "only notify on confidence ≥ 0.8")
- Expanding intake sources or adding new deal classification logic
