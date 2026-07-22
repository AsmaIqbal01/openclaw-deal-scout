# Feature Specification: HubSpot CRM Logger

**Feature Branch**: `002-hubspot-crm-logger`
**Created**: 2026-07-15
**Status**: Draft
**Input**: Log confirmed deals to HubSpot Free CRM with idempotency, rate-limit compliance, and failable pending state

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Confirmed Deal Auto-Logged to HubSpot (Priority: P1)

A Pakistani SMB operator receives a business deal email. The Gmail intake tool (`001-gmail-intake`) classifies it as a confirmed deal and produces a `DealPayload`. Without any manual action, the CRM logger reads that payload and creates a contact record (for the sender) and a linked deal record in the operator's HubSpot Free CRM account.

**Why this priority**: This is the primary value of the feature. Every other story is a safeguard around this core flow.

**Independent Test**: Feed a single `DealPayload` into the CRM logger against a real or sandbox HubSpot account; verify that exactly one contact and one deal appear in HubSpot.

**Acceptance Scenarios**:

1. **Given** a confirmed `DealPayload` with a sender email not previously in HubSpot, **When** the CRM logger runs, **Then** a new HubSpot contact is created with the sender's email and name, and a new HubSpot deal is created and associated with that contact.
2. **Given** a confirmed `DealPayload` with a sender email already in HubSpot, **When** the CRM logger runs, **Then** no new contact is created; the deal is associated with the existing contact.
3. **Given** a `DealPayload` that has already been logged (`crm-logged` in state store), **When** the CRM logger runs again with the same payload, **Then** no HubSpot write is attempted and the state remains `crm-logged`.

---

### User Story 2 — Failed Write Enters Failable Pending State (Priority: P1)

A CRM write fails mid-cycle (HubSpot returns an error, the network drops, or the rate limit is hit). The deal is neither silently discarded nor incorrectly marked as logged. Instead it enters a `crm-pending` state that makes it visible and retryable.

**Why this priority**: Silent data loss destroys operator trust. A failable pending state is the minimum viable safety net.

**Independent Test**: Simulate a HubSpot API failure for one deal; verify the state store shows `crm-pending`, the deal is absent from HubSpot, and no entry is marked `crm-logged`.

**Acceptance Scenarios**:

1. **Given** a confirmed `DealPayload`, **When** the HubSpot API returns an error during the write, **Then** the deal's state is set to `crm-pending` (not `crm-logged`, not absent from the state store).
2. **Given** a deal in `crm-pending` state and a now-healthy HubSpot API, **When** the next poll cycle runs, **Then** the pending deal is retried before new deals are processed, and on success transitions to `crm-logged`.
3. **Given** a deal in `crm-pending` state, **When** the retry also fails, **Then** the state remains `crm-pending` and a WARN log is emitted; the agent continues processing other deals.

---

### User Story 3 — Rate-Limit-Safe Burst Processing (Priority: P2)

When multiple deals arrive in a single poll cycle, the CRM logger writes them to HubSpot at a pace that stays within the burst rate limit. The operator never sees a `429 Too Many Requests` error caused by OpenClaw.

**Why this priority**: A single rate-limit violation could black-list the private app token or disrupt all HubSpot writes for the day.

**Independent Test**: Submit 10 `DealPayload` records in a single batch; verify all 10 appear in HubSpot and no 429 error is logged.

**Acceptance Scenarios**:

1. **Given** N confirmed deals where N × (API calls per deal) ≤ 100, **When** the CRM logger processes them sequentially in one cycle, **Then** all writes complete successfully and no HubSpot 429 error is returned.
2. **Given** a burst of deals that would require more than 100 HubSpot API calls within 10 seconds, **When** the CRM logger processes them, **Then** writes are spaced so the burst limit is never exceeded, even if this extends the poll cycle duration.

---

### User Story 4 — Pending Deals Drain Before New Deals (Priority: P2)

Deals that failed CRM logging in a previous cycle are retried first, ensuring no deal ages out or is indefinitely deferred by a constant stream of new arrivals.

**Why this priority**: Without drain-first ordering, a busy inbox could starve pending deals indefinitely.

**Independent Test**: Seed two `crm-pending` deals and introduce one new deal; verify both pending deals are attempted before the new deal.

**Acceptance Scenarios**:

1. **Given** 2 deals in `crm-pending` and 1 new confirmed deal in the same cycle, **When** the CRM logger runs, **Then** the 2 pending deals are attempted first, then the new deal.

---

### User Story 5 — Per-Cycle Limits, Name Parsing, and Retry Payload Integrity (Priority: P2)

The CRM logger enforces three concrete data-integrity and safety invariants independently of the main write flow: a per-cycle API call circuit breaker, a deterministic sender name split, and full payload persistence for retry without re-querying Gmail.

**Why this priority**: These invariants prevent silent data loss and non-deterministic contact records; they are not covered by the main happy-path scenarios.

**Independent Test**: Run three targeted unit tests against the module in isolation using a mocked HubSpot client and state store.

**Acceptance Scenarios**:

1. **Given** 31 confirmed deals (31 × 3 = 93 API calls, exceeding the FR-011 threshold of 90), **When** the CRM logger runs, **Then** exactly 30 deals are written to HubSpot (90 calls), the remaining deal(s) are placed in `crm-pending` state before the cycle exits, and a WARN log is emitted stating the deferred count.
2. **Given** `sender_name = "Jane Doe Smith"`, **When** `log_deal` is invoked, **Then** the HubSpot contact is created with `firstname = "Jane"` and `lastname = "Doe Smith"`; and **given** `sender_name = "Alice"` (no space), **Then** `firstname = "Alice"` and `lastname` is blank in HubSpot.
3. **Given** a deal placed in `crm-pending` after a HubSpot write failure (full DealPayload persisted per FR-015), **When** the agent restarts and FR-008 runs, **Then** the CRM Logger Module receives a complete 9-field DealPayload reconstructed solely from the state store, with no Gmail API call required.
4. **Given** a `DealPayload` where `subject` is 260 characters long, **When** the CRM logger invokes the HubSpot deal create call, **Then** the `dealname` property sent to HubSpot is exactly 255 characters (the first 252 characters of `subject` followed by `"..."`), and the full 260-character `subject` is present unmodified in `openclaw_deal_summary`.
5. **Given** a `DealPayload` where `subject` is exactly 255 characters, **When** the CRM logger invokes the HubSpot deal create call, **Then** `dealname` is sent as-is with no truncation applied.

---

### Edge Cases

- What happens when HubSpot returns a 429 rate-limit error mid-batch? → The CRM Logger Module receives the full batch of DealPayloads at cycle start (per FR-008). On a 429, already-written deals stay `crm-logged`; the module MUST write a `crm-pending` state-store entry for every deal in the batch that had not yet been attempted before exiting. This keeps the 429 abort fully within the module's own boundary and ensures FR-008 retries all unattempted deals next cycle.
- What happens when HubSpot contact search returns multiple contacts with the same email? → Use the contact with the earliest HubSpot creation date (lowest internal ID); log a WARN including all matched contact IDs; do not create a duplicate.
- What happens when `sender_email` is null, empty, or not a valid email format? → The CRM Logger MUST treat the deal as a write failure per FR-007: place it in `crm-pending`, emit a WARN log with the Gmail message ID and reason `invalid_sender_email`, and advance to the next deal. No HubSpot API call is attempted. `sender_email` is expected non-null and non-empty by the upstream; this edge case is a defensive guard only.
- What happens when the `DealPayload.sender_name` is empty or None? → Create the contact with email only; name fields left blank; do not abort the write.
- What happens when the daily limit is projected to be exceeded? → Log a WARN and defer remaining writes when projected calls would exceed 237,500 (95% of 250,000) — see FR-011. Do not attempt writes beyond that threshold.
- What happens when a HubSpot write succeeds but the state-store update to `crm-logged` fails? → Log an ERROR; leave state as `crm-pending`; accept that the next retry will produce a duplicate HubSpot record; document manual recovery path — see FR-013.
- What happens when the contact upsert succeeds but the deal create call fails (partial write)? → The contact record now exists in HubSpot. On retry, FR-003 will find the existing contact and link the new deal attempt to it. No duplicate contact is created. This is safe and self-correcting.
- What happens when the state store is unreadable at retry time? → Follow the existing `StateStoreReadError` policy from `001-gmail-intake` (log ERROR, skip CRM cycle).
- What happens when the state-store write to `crm-pending` itself fails (after a HubSpot write error)? → The deal is left absent from the state store entirely — not in `crm-pending`, not in `crm-logged`, not visible to FR-008. The system MUST emit an ERROR log containing the Gmail message ID and the I/O error reason. This is the highest-severity silent-drop scenario in the spec; it is not retried automatically. Manual recovery: the operator searches `processed_ids.json` for the absence of the Gmail message ID and re-queues it by manually inserting a `crm-pending` entry. See also FR-013, which covers the symmetric case where the write to `crm-logged` fails after a confirmed HubSpot success.
- What happens when a deal has been in `crm-pending` for more than 24 hours? → Continue retrying; no automatic expiry or escalation in MVP scope.
- What happens when HubSpot returns 401 across multiple consecutive poll cycles? → After 3 consecutive 401 cycles, all CRM writes are suspended and a FATAL log is emitted; the agent continues Gmail polling but makes no further HubSpot calls until the operator rotates the Service Key and restarts the agent — see FR-007 cross-cycle escalation sub-case.
- What happens when `DealPayload.gmail_message_id` is null or empty? → The `gmail_message_id` field is the primary state-store key; without it, neither `crm-pending` nor `crm-logged` can be persisted. The CRM Logger MUST reject the deal immediately: emit an ERROR-level log with the reason `invalid_gmail_message_id` and the value received; make no HubSpot API call; return `crm-pending` without any state-store write (accepting that this deal is a silent drop with no retry path). This is a defensive guard only — `001-gmail-intake` guarantees a non-null, non-empty `gmail_message_id` on every `DealPayload`; if this guard fires, it indicates an upstream contract violation that requires investigation of the `001-gmail-intake` output before any retry is possible.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept a `DealPayload` record (all 9 fields) as the input unit for each CRM log operation.
- **FR-002**: Before any HubSpot write, the system MUST check the state store for the deal's Gmail message ID. If the outcome is already `crm-logged`, the write MUST be skipped entirely.
- **FR-003**: The system MUST search HubSpot for an existing contact by sender email before creating a new contact. If a match exists, the new deal MUST be linked to that contact; no new contact record is created.
- **FR-004**: The system MUST create a HubSpot deal record populated with: deal name (from `subject`), deal category, confidence score, deal summary, received date, and the Gmail message ID as a traceability reference. If `subject` exceeds 255 characters, the deal name MUST be truncated to 252 characters and appended with `...` before the HubSpot write; the full subject remains available in `deal_summary` and is unaffected by this truncation.
- **FR-005**: The system MUST authenticate to HubSpot exclusively via a static private-app Service Key token read from the environment variable `HUBSPOT_PRIVATE_APP_TOKEN`, stored in `.env` and absent from version control. No interactive login, browser OAuth, or runtime credential prompt is permitted.
- **FR-006**: The system MUST space sequential HubSpot API calls such that no more than 100 calls are issued in any rolling 10-second window per private app — the verified burst limit for HubSpot Free tier (source: `developers.hubspot.com/docs/developer-tooling/platform/usage-guidelines`, July 2026). This constraint applies across all call types (contact search, contact create/update, deal create) within a single poll cycle. The mandated inter-call spacing mechanism is defined in constitution Principle VI: a minimum 100 ms delay MUST be inserted between sequential HubSpot API calls. This yields a safe sustained throughput of approximately 10 calls/second (~200 deals/minute at 3 calls/deal). The plan MUST implement this 100 ms delay; no alternative spacing mechanism is permitted without a constitution amendment. Each individual API call placed into the outbound queue MUST be logged at DEBUG level with its Gmail message ID, call type, and queue position.
- **FR-007**: On any HubSpot write failure — network error, timeout, non-401 4xx, 5xx, or a 200 response whose body is missing an expected field (e.g. contact ID from search, or deal ID from create) — the affected deal MUST be placed in `crm-pending` state in the state store and a WARN log MUST be emitted. The deal MUST NOT be silently discarded and MUST NOT be marked `crm-logged`. **401 sub-case (within-cycle)**: if HubSpot returns 401, the system MUST emit an ERROR-level log (not WARN), place the current deal in `crm-pending`, and pause all remaining HubSpot writes for the rest of the poll cycle. Subsequent deals in the same cycle MUST also be placed in `crm-pending` without attempting any write. The 401 case MUST NOT be retried within the same cycle. This behaviour mirrors the constitution Principle VI pattern for unrecoverable credential failures. **401 sub-case (cross-cycle escalation)**: the system MUST track a persistent consecutive-401-cycle counter (JSON key: `consecutive_401_cycles`) in the state store. If HubSpot returns 401 in **3 or more consecutive poll cycles**, the system MUST suspend all HubSpot CRM writes for all subsequent cycles and emit a FATAL-level log entry: `[FATAL] HubSpot credential invalid — CRM writes suspended; operator action required`. The consecutive-401 counter MUST reset to zero on any successful HubSpot API response. **Counter semantics**: A cycle is counted as a consecutive-401 cycle only if it produces at least one 401 response and zero successful HubSpot responses; a success anywhere in the cycle resets the counter and the cycle is not counted. Cycles in which no HubSpot API calls are attempted (no pending deals, no new deals) do not increment or reset the counter. The counter is incremented by exactly 1 at the conclusion of each poll cycle that qualifies as a 401 cycle — not per individual 401 response within that cycle. **Suspension behavior (takes precedence over FR-008)**: during CRM-suspended mode (`consecutive_401_cycles` ≥ 3), FR-008 state-store inspection is bypassed entirely. The CRM logging cycle MUST emit a single INFO log — `[INFO] CRM writes suspended (consecutive_401_cycles=N); skipping cycle` — and return immediately without attempting any HubSpot API calls or advancing any deal state. Newly confirmed `deal_extracted` deals from the same Gmail poll cycle remain in `deal_extracted` state during suspension and are not advanced to `crm-pending`; they accumulate in `deal_extracted` and will be picked up by FR-008 on the first non-suspended cycle after the operator rotates the Service Key and restarts. **Recovery on restart**: on agent startup, if `consecutive_401_cycles` is 3 or more, the system MUST emit a WARN-level log (`[WARN] Starting in CRM-suspended mode; consecutive_401_cycles = N`) and then reset the counter to 0 so that the next successful HubSpot API response confirms the rotated key is valid. If the operator restarts without rotating the key, the first 401 response in the new session begins a fresh three-cycle count before suspension re-activates.
- **FR-008**: At the start of each CRM logging cycle, the system MUST inspect the state store for all deals in `crm-pending` state and attempt to write them to HubSpot before processing newly confirmed deals. Both `crm-pending` retries and `deal_extracted` new deals are available as full DealPayloads from the state store (all nine fields are persisted per FR-015); the CRM Logger Module is invoked once per deal with only a `DealPayload` as input and determines first-attempt vs retry status internally via FR-002.
- **FR-009**: A deal's state MUST transition to `crm-logged` ONLY upon receiving a successful confirmation response from HubSpot that includes a valid resource ID (contact ID or deal ID as applicable). Sending the request is not sufficient; a 200 with a missing resource ID is treated as a failure per FR-007.
- **FR-010**: Every HubSpot write failure MUST produce a WARN-level log entry containing the Gmail message ID, the failure reason, and the resulting state (`crm-pending`). A successful write MUST produce an INFO-level log entry containing the Gmail message ID, the HubSpot deal ID, and the resulting state (`crm-logged`).
- **FR-011**: The system MUST maintain a local per-cycle call counter that increments for every HubSpot API call attempted within a single poll cycle (contact search, contact upsert, deal create). If this per-cycle counter reaches or exceeds **90 calls** before the cycle completes, the system MUST log a WARN and defer all remaining unprocessed deals for that cycle; deferred deals MUST be placed in `crm-pending` state before the cycle ends so FR-008 retries them next cycle. **Scope note**: this counter is a per-cycle circuit breaker, not a cumulative daily quota guard. Daily quota accumulation across cycles is outside MVP scope because at the expected workload ceiling for this deployment (≤ 50 confirmed deals per day × 3 calls per deal = ≤ 150 calls/day), the 250,000/day account limit is unreachable by several orders of magnitude. If daily call volumes ever approach 83,000 (33% of the daily limit), a constitution amendment and daily-counter feature are required.
- **FR-012**: If the HubSpot contact-search call returns a non-200 response or times out, the system MUST treat the entire deal as a write failure per FR-007: place it in `crm-pending`, emit a WARN log with the Gmail message ID and search error reason, and advance to the next deal. The failed search MUST NOT be retried within the same poll cycle.
- **FR-013**: If HubSpot returns a success confirmation (FR-009 trigger) but the subsequent state-store write to `crm-logged` fails due to an I/O error, the system MUST log an ERROR entry with the Gmail message ID and the I/O error reason. The deal MUST remain in `crm-pending` state. **Known duplicate risk**: on the next retry cycle, FR-008 will re-attempt the write, producing a second HubSpot deal record for the same Gmail message ID. This is the one scenario where SC-002 cannot be fully enforced automatically. Manual recovery: operator deletes the duplicate HubSpot deal record and corrects or removes the `crm-pending` state entry. See also the Edge Case for crm-pending write failure, which covers the symmetric scenario where the I/O error occurs while writing `crm-pending` (producing a silent drop rather than a duplicate).
- **FR-014**: `sender_name` MUST be split into `firstname` and `lastname` using the following unambiguous rule: split on the first space character only — everything before the first space is `firstname`, everything after (including any further spaces) is `lastname`. If `sender_name` contains no space, the entire value is `firstname` and `lastname` is left blank. If `sender_name` is null or empty, both fields are left blank. Contact creation MUST succeed regardless of whether name fields are populated.
- **FR-015**: When the state store records a `deal_extracted`, `crm-pending`, or `crm-logged` outcome for a message, the entry MUST persist all nine DealPayload fields alongside the base `ProcessedMessage` fields (`gmail_message_id`, `processed_at`, `outcome`). The nine additional fields are: `sender_email`, `sender_name`, `subject`, `received_at`, `deal_summary`, `deal_category`, `confidence_score`, `raw_email_excerpt`, and `gmail_message_id` (already present as primary key). This persistence contract enables the CRM Logger Module to receive a complete DealPayload for any retry without re-fetching from Gmail.

### Key Entities

- **DealPayload** (input, from `001-gmail-intake`): The 9-field typed record representing a confirmed deal. Field types are defined in `specs/001-gmail-intake/data-model.md`; key fields used here: `gmail_message_id` (string, unique, non-null, non-empty — primary state-store key; the CRM Logger MUST apply the `invalid_gmail_message_id` defensive guard (see Edge Cases) if this precondition is violated), `sender_email` (string, non-null, non-empty, valid email format — primary HubSpot contact dedup key; the CRM Logger MUST validate this precondition and fail safely per the `invalid_sender_email` edge case if violated), `sender_name` (string or null), `subject` (string), `received_at` (ISO-8601 UTC string), `deal_summary` (string, max 500 chars), `deal_category` (enum: lead | partnership_inquiry | vendor_offer | rfq | other), `confidence_score` (float 0.0–1.0), `raw_email_excerpt` (string or null, max 500 chars). Consumed as-is; no schema changes to upstream.
- **CrmLogEntry** (state store extension): Inherits all fields of `ProcessedMessage` from `001-gmail-intake` (`gmail_message_id`: string, `processed_at`: ISO-8601 UTC string, `outcome`: string). Adds two new `outcome` values: `crm-pending` (write attempted and failed; eligible for retry) and `crm-logged` (write confirmed by HubSpot). Existing `ProcessedMessage` outcome values are unchanged. For entries with outcome `deal_extracted`, `crm-pending`, or `crm-logged`, the full DealPayload MUST also be persisted alongside the base fields so the CRM Logger Module can be supplied the complete payload on retry without re-fetching from Gmail. The nine additional fields stored are: `sender_email` (string), `sender_name` (string or null), `subject` (string), `received_at` (ISO-8601 UTC string), `deal_summary` (string), `deal_category` (enum string), `confidence_score` (float), `raw_email_excerpt` (string or null), and `gmail_message_id` (already present as the primary key). Entries with other outcomes (e.g. `not_a_deal`, `body_absent`) do NOT store the extended payload fields.
- **HubSpotContact**: A HubSpot contact record keyed by sender email. Attributes written by this feature: `email` (from `sender_email`; primary dedup key), `firstname` and `lastname` (parsed from `sender_name`; may be blank if `sender_name` is null). Read attribute: HubSpot internal creation date (used for dedup resolution when multiple contacts share the same email).
- **HubSpotDeal**: A HubSpot deal record linked to a `HubSpotContact`. Attributes written by this feature and their HubSpot API property keys:
  - Deal name → `dealname` (standard HubSpot property); truncated per FR-004 if `subject` exceeds 255 chars
  - Deal category → `openclaw_deal_category` (custom, single-line text; must be pre-created)
  - Confidence score → `openclaw_confidence_score` (custom, decimal number; must be pre-created)
  - Deal summary → `openclaw_deal_summary` (custom, multi-line text; must be pre-created)
  - Received date → `openclaw_received_date` (custom, date property stored as Unix milliseconds; must be pre-created)
  - Gmail message ID → `openclaw_gmail_message_id` (custom, single-line text; must be pre-created)
  Associated contact set at creation time via HubSpot association API. **Deployment prerequisite**: the five `openclaw_*` custom properties (`openclaw_deal_category`, `openclaw_confidence_score`, `openclaw_deal_summary`, `openclaw_received_date`, `openclaw_gmail_message_id`) MUST be created in the operator's HubSpot Free account before the feature can run; this is a one-time manual setup step, not a runtime operation.
- **CRM Logger Module** (boundary): Accepts exactly one `DealPayload` per invocation — no additional parameters. Invocation signature: `log_deal(payload: DealPayload) -> Literal["crm-logged", "crm-pending", "skipped"]`. The module determines internally whether the deal is a first attempt or a retry by reading the state store (FR-002); the caller does not need to pass an outcome label. Returns one of three outcomes: `crm-logged` (HubSpot write confirmed with valid resource ID), `crm-pending` (write failed; eligible for retry next cycle — **exception**: when returned by the `invalid_gmail_message_id` defensive guard, no state-store entry is written and no retry is possible; this return signals an upstream contract violation, not a retryable CRM failure), or `skipped` (already `crm-logged` in state store, per FR-002). Raises no unhandled exceptions — all errors are caught, logged, and expressed as `crm-pending` or `skipped` outcomes.
- **State Store Schema** (`processed_ids.json`): The top-level document is a JSON object with three keys: `last_poll_time` (ISO-8601 UTC string or null), `consecutive_401_cycles` (integer, default 0), and `messages` (array of message entries). The `consecutive_401_cycles` counter is a top-level sibling to `messages`, not nested inside any message entry. Example structure:

  ```json
  {
    "last_poll_time": "2026-07-15T10:00:00Z",
    "consecutive_401_cycles": 0,
    "messages": [
      {
        "gmail_message_id": "abc123",
        "processed_at": "2026-07-15T10:01:00Z",
        "outcome": "crm-pending",
        "sender_email": "vendor@example.com",
        "sender_name": "Vendor Corp",
        "subject": "Partnership Proposal",
        "received_at": "2026-07-15T09:55:00Z",
        "deal_summary": "Vendor Corp proposes a distribution partnership.",
        "deal_category": "partnership_inquiry",
        "confidence_score": 0.92,
        "raw_email_excerpt": "We are interested in partnering with your firm..."
      },
      {
        "gmail_message_id": "def456",
        "processed_at": "2026-07-15T10:02:00Z",
        "outcome": "crm-logged",
        "sender_email": "buyer@example.com",
        "sender_name": "Buyer Ltd",
        "subject": "RFQ: Office Supplies",
        "received_at": "2026-07-15T09:58:00Z",
        "deal_summary": "Buyer Ltd requests a quote for office supplies.",
        "deal_category": "rfq",
        "confidence_score": 0.88,
        "raw_email_excerpt": "Please send us a quote for 500 units..."
      }
    ]
  }
  ```

  All nine DealPayload fields are retained in `crm-logged` entries (same as `crm-pending`) to support audit and dedup verification. Entries with other outcomes (e.g. `not_a_deal`, `body_absent`) do NOT include the extended payload fields.

- **ConsecutiveAuthFailureCounter** (state store field, JSON key: `consecutive_401_cycles`): A single integer persisted in the state store alongside processed messages. Full lifecycle governed by FR-007 Counter semantics: (a) Incremented by 1 at the conclusion of any poll cycle in which at least one 401 response was received **and** zero successful HubSpot responses occurred in that same cycle. (b) Reset to 0 immediately upon any successful HubSpot API response within a poll cycle; any subsequent 401 in the same cycle does not re-increment the counter — the cycle is classified as non-401 and the counter remains 0 at cycle end. (c) Reset to 0 on agent startup if the persisted value is 3 or more (recovery from suspended mode), per FR-007 Recovery on restart — this is the only mechanism by which suspension is lifted, since no HubSpot calls are made during suspension. (d) If this field is absent from the state store (first run or clean deployment), it MUST be treated as 0. Cycles in which no HubSpot API calls are attempted do not modify the counter. When this value reaches 3, CRM writes are suspended and the FATAL log is emitted per FR-007.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every confirmed `DealPayload` appears as a matched contact + linked deal in HubSpot within one poll cycle of detection, with zero manual operator action required.
- **SC-002**: Zero duplicate HubSpot deal records for the same Gmail message ID, verified across unlimited sequential poll cycles. Exception: the FR-013 state-store I/O failure scenario may produce a single duplicate on the next retry cycle; this is acknowledged behavior requiring manual recovery per FR-013 and does not constitute a test failure.
- **SC-003**: Zero duplicate HubSpot contact records for the same sender email address, verified across unlimited sequential poll cycles.
- **SC-004**: Every HubSpot write failure produces a `crm-pending` state store entry — zero silent drops confirmed by inspecting the state store after a simulated failure. Exception: the crm-pending write failure scenario (where the state-store write to `crm-pending` itself fails after a HubSpot error) will leave the deal absent from the state store; this is an acknowledged silent drop requiring manual recovery per the crm-pending write failure edge case and does not constitute a test failure when that specific compound failure is simulated.
- **SC-005**: Deals in `crm-pending` state transition to `crm-logged` within 2 poll cycles of the underlying failure being resolved, with no manual operator intervention.
- **SC-006**: N sequential deals (where N × 3 API calls ≤ 100) complete in a single poll cycle without triggering a HubSpot 429 burst-limit error. (3 calls per deal = contact search + contact upsert + deal create.)
- **SC-007**: The agent continues polling Gmail and processing new deals after any HubSpot write failure — no crash, no halt, no operator restart required.

---

## Constitution Check Gates

All 6 gates from `constitution.md §Technology Stack & Architecture` are evaluated explicitly:

| Gate | Question | Verdict | Rationale |
|------|----------|---------|-----------|
| 1 | Does this introduce any paid dependency? | **PASS** | HubSpot Free CRM + private-app Service Key = zero cost. No credit card required. |
| 2 | Does this add a non-Gmail intake source to the MVP pipeline? | **PASS** | Consumes `DealPayload` output from `001-gmail-intake`; no new intake channel introduced. |
| 3 | Does this require a runtime browser login? | **PASS** | Service Key is a static token in `.env`; fully non-interactive (Principle III). |
| 4 | Does this risk duplicate CRM entries or duplicate alerts? | **CONDITIONAL PASS** | FR-002 (idempotency by Gmail message ID) + FR-003 (contact dedup by email) prevent duplicates under normal operation. One known exception: FR-013 documents a scenario where a confirmed HubSpot write is followed by a state-store I/O failure, leaving the deal in `crm-pending` and causing a duplicate write on retry. This risk is acknowledged, bounded, and has a defined manual recovery path. |
| 5 | Does this modify core pipeline files to add a new notification target? | **PASS** | New isolated `crm_logger` module; no changes to `001-gmail-intake` or any notifier code. |
| 6 | Does this allow an exception to crash the agent? | **PASS** | FR-007 (failable pending state) + FR-010 (WARN log) + SC-007 (no crash) enforce Principle VI. |

---

## Assumptions

- HubSpot Free tier burst limit: **100 requests per 10 seconds per private app** — verified from `developers.hubspot.com/docs/developer-tooling/platform/usage-guidelines`, July 2026.
- HubSpot Free tier daily limit: **250,000 requests per account per day** — same source.
- Each deal requires exactly 3 HubSpot API calls: (1) contact search, (2) contact create or update, (3) deal create. The mandated inter-call delay is 100 ms as specified in FR-006, yielding a sustained throughput of approximately 10 calls/second (~200 deals/minute at 3 calls/deal).
- HubSpot's native contact deduplication key is email address; no custom dedup logic is required beyond the email-based search in FR-003.
- The `DealPayload` schema from `001-gmail-intake` is stable and consumed as-is; no changes to its type definition or field contract are required. However, FR-015 requires that `deal_extracted` state-store entries in `processed_ids.json` carry all nine DealPayload fields. Since `001-gmail-intake`'s current `ProcessedMessage` write path persists only three fields (`gmail_message_id`, `processed_at`, `outcome`), a targeted change to `001-gmail-intake`'s state-store write path is needed to add the nine payload fields to `deal_extracted` entries. This is an implementation dependency, not a DealPayload schema change.
- The existing `processed_ids.json` state store is extended with two new `outcome` values (`crm-pending`, `crm-logged`). The `001-gmail-intake` outcomes (`deal_extracted`, `not_a_deal`, etc.) are unaffected.
- `sender_name` may be `None`; contact creation MUST succeed with email-only in that case.
- A "poll cycle" for this feature = one execution of the CRM logger after `check_new_deals` has run.

## Out of Scope

- Discord / Slack / email notifications (feature `003`)
- Writing `raw_email_excerpt` to HubSpot — this field is available in `DealPayload` but is intentionally excluded from HubSpot deal records to avoid storing raw email content in the CRM
- HubSpot deal pipeline stage management or deal owner assignment
- HubSpot data deletion, archival, or GDPR-related erasure
- Paid HubSpot tiers or API limit increases
- Any new Gmail or non-Gmail intake source
- Automatic `crm-pending` expiry or escalation (no TTL in MVP)
- HubSpot company record creation (contacts only, for MVP)
