# ADR-0003: CRM Write Failable-Pending State and Circuit-Breaker Pattern

- **Status:** Accepted
- **Date:** 2026-07-16
- **Feature:** hubspot-crm-logger (002-hubspot-crm-logger); recommended pattern for 003-discord-notification
- **Context:** The HubSpot CRM write step is an external network call that can fail for
  reasons outside the pipeline's control: network errors, HubSpot API errors (4xx/5xx),
  rate-limit exhaustion (429), or invalid credentials (401). A deal that fails to write
  must not be silently discarded (loses operator data), must not crash the agent (violates
  Constitution Principle VI), and must not block the pipeline on a synchronous retry that
  may itself fail. Separately, the HubSpot Free tier imposes a burst limit of 100 API
  calls per 10-second window. Processing many deals in one poll cycle risks hitting this
  limit. A third concern: if HubSpot credentials are invalid (401), the pipeline must
  detect the pattern across multiple cycles and suspend writes rather than flooding
  HubSpot with bad-credential calls indefinitely.
  These three concerns (write failure recovery, rate-limit compliance, credential failure
  escalation) are addressed together because they share a common mechanism: deferring
  in-flight work to a persistent pending state rather than attempting it synchronously.

## Decision

Use a **failable-pending write pattern** with a **per-cycle circuit breaker** and a
**consecutive-failure suspension gate**:

### 1. Failable-Pending State (`crm-pending`)

Any HubSpot write failure — network error, timeout, non-401 4xx, 5xx, 200 with
missing resource ID, or invalid `sender_email` — writes a `crm-pending` entry to the
state store and emits a WARN log. The deal is never silently dropped and the agent
never crashes. The `crm-pending` outcome carries all 9 DealPayload fields so the deal
can be retried on the next cycle without re-querying Gmail.

```
HubSpot write failure
       │
       ▼
write_crm_outcome(id, "crm-pending")  ← atomic, merge-write (preserves other state)
       │
       ▼
WARN log: [gmail_message_id, failure_reason, "crm-pending"]
       │
       ▼
continue processing next deal
```

### 2. Drain-First Retry Ordering

At the start of each CRM cycle, all `crm-pending` entries are processed before new
`deal_extracted` entries. This guarantees that a constant stream of new deals cannot
starve pending retries indefinitely.

```
run_crm_cycle():
  1. get_pending_deals() → retry each via log_deal()
  2. get_new_deals()    → process each via log_deal()
```

### 3. 100ms Inter-Call Delay (Rate-Limit Compliance)

`HubSpotClient._call()` inserts `time.sleep(0.1)` after every non-401 response.
This yields a safe sustained throughput of ≤10 calls/second — below HubSpot Free's
100 calls/10s burst limit. The delay is enforced at a single point in `_call()` so
it cannot be accidentally omitted by any calling method.

### 4. Per-Cycle Call Counter Circuit Breaker (FR-011)

`run_crm_cycle()` checks `client.call_count >= 90` before processing each deal.
When reached, all remaining unprocessed deals are written to `crm-pending` and the
cycle exits with a WARN log. This keeps any single cycle within a safe fraction of
HubSpot's burst limit (90 calls ≈ 30 deals × 3 calls/deal), leaving headroom for
burst variance.

### 5. Consecutive-401 Suspension Gate (FR-007 Cross-Cycle)

A `consecutive_401_cycles` counter is persisted as a top-level key in
`processed_ids.json`. A cycle increments the counter only if it produced ≥1 401
response AND 0 successful HubSpot responses. Any successful response resets the
counter to 0. When the counter reaches 3, the pipeline emits a FATAL log and suspends
all CRM writes for all subsequent cycles:

```
consecutive_401_cycles ≥ 3:
  → INFO: "CRM writes suspended; skipping cycle"
  → return CrmCycleResult(suspended=True, ...)
  → (Gmail polling continues unaffected)
```

Recovery: operator rotates the private-app token, updates `HUBSPOT_PRIVATE_APP_TOKEN`
in `.env`, and restarts the agent. On restart, `run_crm_cycle()` detects
`consecutive_401_cycles ≥ 3`, emits a WARN, resets the counter to 0, and re-enters
normal operation. If the rotated token is still invalid, the three-cycle count begins
fresh.

## Consequences

### Positive

- **No silent data loss**: Every failed HubSpot write produces a `crm-pending` entry
  that is visible in `processed_ids.json` and retried automatically. An operator can
  audit the file to find all pending deals.
- **Agent never crashes on write failure**: Constitution Principle VI is satisfied by
  construction — all write failures are caught and expressed as `crm-pending` outcomes.
- **Self-healing under transient failures**: When HubSpot recovers (after a brief
  outage or network blip), pending deals drain automatically on the next cycle with no
  operator action required (SC-005: within 2 poll cycles of failure resolution).
- **Burst-safe by default**: The 100ms delay and 90-call circuit breaker mean the
  pipeline never triggers HubSpot's burst-limit error regardless of deal volume,
  without requiring the caller to manage delays.
- **Credential failure is visible and bounded**: The 3-cycle suspension gate prevents
  the pipeline from making hundreds of bad-credential calls before the operator notices.
  The FATAL log is unmissable; the restart-reset recovery is a one-step fix.
- **Persistent counter survives restarts**: `consecutive_401_cycles` is in the shared
  state store, not in memory — a process restart does not silently reset a suspension
  that the operator has not acknowledged.
- **Pattern is reusable**: The same failable-pending + drain-first + circuit-breaker
  structure applies directly to the Discord notification step (003) and any future
  external write step (email, Slack, webhook).

### Negative

- **Deals may be delayed by up to N cycles**: A deal that fails on cycle K will not be
  retried until cycle K+1. If failures persist (e.g., HubSpot is down for hours), the
  deal accumulates in `crm-pending` for as many cycles as the outage lasts. There is no
  automatic escalation or operator alert beyond the WARN logs and the FATAL at 3×401.
- **Duplicate HubSpot records on partial state-store failure**: If a HubSpot write
  succeeds but the subsequent `crm-logged` state-store write fails (FR-013), the deal
  stays `crm-pending` and will be retried — producing a duplicate deal record in HubSpot.
  This is a known, bounded exception (FR-013 manual recovery path) accepted in exchange
  for the simpler write model.
- **State store grows with pending entries**: Deals stuck in `crm-pending` indefinitely
  (e.g., due to a HubSpot account issue unrelated to credentials) accumulate in
  `processed_ids.json`. The existing 50 MB warn threshold from ADR-0002 provides the
  only signal; no automatic expiry exists in MVP.
- **90-call limit is conservative**: At 3 calls/deal, 90 calls = 30 deals/cycle. Under
  normal load (≤50 deals/day) this is never hit. During a catch-up burst (many `crm-pending`
  entries from an outage), cycles may process only 30 deals at a time, extending recovery
  time. This is the correct trade-off: safety over speed.
- **Suspension requires manual restart**: When CRM writes are suspended, the operator must
  actively rotate the token and restart. There is no automatic token refresh or health-check
  ping to detect when HubSpot is reachable again. This is intentional: credential rotation
  is a security-sensitive action that should require operator intent.

## Applicability to Feature 003 (Discord Notification)

The constitution (Principle VI, failure table) already names the parallel state for
Discord notification failures: `crm-logged-notify-pending`. Feature 003 SHOULD implement
the same failable-pending + drain-first pattern:

| Component | 002 (HubSpot) | 003 (Discord) — recommended |
|---|---|---|
| Failure outcome | `crm-pending` | `notify-pending` |
| Retry order | drain `crm-pending` before new | drain `notify-pending` before new |
| Rate-limit delay | 100ms between HubSpot calls | Discord webhook: 1 req/s per webhook (if applicable) |
| Circuit breaker | 90 calls/cycle | Discord: no hard per-cycle cap; per-minute webhook limits apply |
| Credential suspension | 3× consecutive 401 cycles → FATAL | 3× consecutive auth failures → FATAL |

The specific rate-limit parameters for Discord differ (Discord's per-webhook rate limit
is lower-frequency than HubSpot's burst limit), but the structural pattern — failable
pending state, drain-first retry, per-cycle call guard — is directly applicable and
SHOULD be adopted in 003's plan to maintain a consistent failure model across the
pipeline.

Whether feature 003 adds a separate `notify-pending` outcome or reuses an extended
`crm-logged-notify-pending` value (as the constitution names it) should be decided in
003's spec. Either way, the mechanism described in this ADR is the recommended template.

## Alternatives Considered

### Alternative A — Synchronous in-cycle retry (exponential back-off, 3 attempts)

- **Model**: On write failure, wait and retry up to 3 times within the same poll cycle
  before giving up and writing `crm-pending`
- **Pros**: Deals that fail due to brief transient errors (sub-second network blip) recover
  within the same cycle without leaving a `crm-pending` trace in the state store.
- **Rejected because**: A 3-retry × exponential back-off adds up to 7+ seconds of blocking
  time per failing deal within the cycle. For a burst of 10 deals all failing (e.g., HubSpot
  API down), the cycle blocks for 70+ seconds — far exceeding the expected poll interval.
  Systematic failures (401, sustained outage) burn all retries with no benefit. The
  `crm-pending` trace is a feature, not a bug: it provides an audit record of exactly which
  deals failed and when.

### Alternative B — Silent drop (log and discard)

- **Model**: Log an ERROR when a write fails; discard the deal
- **Pros**: Simplest implementation; no state change required on failure
- **Rejected because**: Permanently loses deal data that the operator may never recover.
  The operator's entire value proposition is that every confirmed deal reaches HubSpot.
  Silent drops destroy that guarantee and the operator trust it depends on.

### Alternative C — Crash the agent on write failure

- **Model**: Raise an unhandled exception on HubSpot write failure; let the systemd
  service restart the agent
- **Pros**: Systemd auto-restart means the deal will be retried on next start; simple
  failure signal (agent down = something is wrong).
- **Rejected because**: Explicitly prohibited by Constitution Principle VI ("an unattended
  agent that crashes silently provides no value"). A crash discards all in-flight work
  for the current poll cycle. systemd restart delay (typically 5–10s) plus agent startup
  time means a crash costs several seconds per failure. Multiple crashes in quick
  succession trigger systemd's failure backoff, potentially pausing the pipeline for
  minutes.

### Alternative D — Separate dead-letter queue file (`crm_failures.json`)

- **Model**: Write failed deals to a separate `crm_failures.json` file; a separate
  drain process reads and retries it
- **Pros**: Clean separation between "processed" (main state store) and "failed" (DLQ);
  easier to inspect just the failures.
- **Rejected because**: Introduces a second file requiring its own lock, own atomic-write
  logic, and own reader/writer pair. The shared `processed_ids.json` already provides the
  same visibility via `outcome="crm-pending"` filtering. Two files create a consistency
  risk: a deal could exist in both files (if the main-store write succeeds but the
  `crm_failures.json` delete fails). The single-file approach from ADR-0002 is the
  established pattern.

### Alternative E — No 401 suspension; retry every cycle regardless

- **Model**: Continue attempting HubSpot writes on every cycle even after repeated 401s;
  log WARN per-cycle
- **Pros**: Simpler orchestrator logic (no suspension state); deals never get "stuck" in
  suspension due to an operator forgetting to restart.
- **Rejected because**: A pipeline that continues flooding HubSpot with bad-credential
  requests across cycles provides a misleading signal (the WARN log is just noise) and
  risks rate-limiting the private-app token for other uses. The FATAL + suspension is an
  unambiguous signal requiring operator action; the 3-cycle threshold provides tolerance
  for brief, transient 401s (token propagation delay, HubSpot hiccup) without triggering
  on a single cycle.

## References

- Feature Spec: `specs/002-hubspot-crm-logger/spec.md` (FR-007, FR-008, FR-011, SC-004, SC-005, SC-007, US2, US3, US5)
- Implementation Plan: `specs/002-hubspot-crm-logger/plan.md`
- Research (Decision 3 — 100ms delay, Decision 9 — suspension bypass): `specs/002-hubspot-crm-logger/research.md`
- Data Model (ConsecutiveAuthFailureCounter, CrmCycleResult, state transitions): `specs/002-hubspot-crm-logger/data-model.md`
- Module Contract (run_crm_cycle, log_deal error handling): `specs/002-hubspot-crm-logger/contracts/crm-logger-contract.md`
- Tasks implementing this pattern: T018–T022 (failable-pending), T023–T026 (rate-limit), T027–T029 (drain-first), T035–T037 (401 suspension)
- Related ADRs: ADR-0001 (Python FastMCP Subprocess Runtime), ADR-0002 (JSON File State Store Mechanism)
- Constitution: Principle VI (Graceful Degradation & Error Resilience) — failure table row "HubSpot rate limit (100 req/10 s)"
- Evaluator Evidence: `history/prompts/hubspot-crm-logger/021-hubspot-crm-logger-tasks-generated.tasks.prompt.md`
