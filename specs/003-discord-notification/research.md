# Research: Discord Deal Notification

**Feature**: `003-discord-notification`
**Date**: 2026-07-17
**Status**: Complete — all NEEDS CLARIFICATION resolved

---

## Decision 1: Discord Webhook Rate Limits

**Decision**: The adapter MUST respect Discord's 30-request-per-60-second per-webhook limit. On HTTP 429, read `retry_after` from the response body (float, seconds) but do NOT sleep within the cycle — mark the deal `crm-logged-notify-pending` and retry on the next scheduled cycle.

**Rationale**: At the pipeline scale (< 50 deals/day expected), we will rarely approach 30/60 s. The 429 response body `{"message": "...", "retry_after": 2.5, "global": false}` gives precise backoff data; however sleeping in the cycle would block the notification server process. Deferring to the next cycle is consistent with the CRM-logger's 429 policy.

**Alternatives considered**:
- Sleep for `retry_after` seconds: rejected — blocks the FastMCP server process; the spec explicitly prohibits within-cycle retry on 429.
- Track `X-RateLimit-Remaining` proactively: deferred — unnecessary at current scale; add as a future enhancement if throughput grows.

**Implementation note**: Extract `retry_after` from JSON response body and include it in the `notify_error_reason` field: e.g. `"429 Too Many Requests (retry_after=2.5s)"`.

---

## Decision 2: Discord Embed Truncation Strategy

**Decision**: Truncate embed fields **before** the HTTP POST to stay within Discord's hard limits. HTTP 400 is returned (not silent truncation) if limits are exceeded. Truncation rules:

| Field | Discord Limit | Truncation rule |
|-------|--------------|-----------------|
| `title` (subject) | 256 chars | Truncate to 253 chars + `"..."` |
| `description` (deal_summary) | 4096 chars | Already ≤ 500 chars from Step 1; no truncation needed |
| Field `value` (sender, category, confidence) | 1024 chars | All values well under 100 chars; no truncation needed |
| Total embed | 6000 chars | Unreachable given above truncations; no additional guard needed |

**Rationale**: The step-2 `truncate_dealname` already caps `subject` at 255 chars, so the 256-char embed title limit is already satisfied. However, `formatter.py` should apply its own 256-char guard defensively (in case upstream truncation changes). Returning HTTP 400 from Discord would leave the deal in `crm-logged` with no error_reason — a worse outcome than pre-truncating.

**Alternatives considered**:
- No client-side truncation, rely on Discord 400: rejected — 400 is not a retryable state; the deal would loop indefinitely.

---

## Decision 3: No Discord Idempotency Key

**Decision**: Every Discord webhook POST creates a new message. There is no request-level deduplication mechanism. The state-store status check (`status == "discord-notified"` → no-op) is the **only** safeguard against duplicate Discord messages.

**Rationale**: This is a Discord API constraint, not a design choice. The implication is that the "delivery-success / state-write-failure" edge case (FR-016) can result in a duplicate Discord message on retry. This is explicitly documented as an at-least-once delivery trade-off in the spec's edge cases section.

**No alternatives**: No workaround exists at the Discord API level.

---

## Decision 4: `typing.Protocol` for NotifierContract

**Decision**: Use `typing.Protocol` (structural subtyping) rather than `abc.ABC`.

**Rationale**:
- Test doubles can be plain classes; no import of the Protocol class required in test files.
- `@runtime_checkable` decorator enables `isinstance()` checks if ever needed.
- `DiscordAdapter` and `NoopAdapter` satisfy the protocol implicitly — adding a new adapter never requires touching the Protocol definition or inheriting from a base class.
- Python 3.12 makes Protocol first-class; no compatibility concerns.

**Alternatives considered**:
- `abc.ABC`: Requires explicit `class DiscordAdapter(NotifierContract)` inheritance. Tightly couples every adapter to the base class import. Rejected.

---

## Decision 5: `requests` Timeout Configuration

**Decision**: Use `timeout=(5, 10)` — connect timeout 5 seconds, read timeout 10 seconds — rather than `timeout=10` (which applies the same value to both).

**Rationale**: A 5-second connect timeout catches DNS and network unreachability quickly. A 10-second read timeout gives Discord's CDN time to respond under moderate load. Using `timeout=10` sets both to 10 s, which means a hung connection attempt could block for twice as long as necessary. `(5, 10)` is the recommended production form per the `requests` library documentation.

**Implementation note**: `requests.post(url, json=body, timeout=(5, 10))` raises `requests.exceptions.Timeout` on either connect or read timeout expiry. Catch this as `DiscordTimeoutError`.

---

## Decision 6: Webhook URL Validation Strategy

**Decision**: At `DiscordAdapter.__init__`, raise `EnvironmentError` immediately if `webhook_url` is empty or None. Do NOT validate the URL format (regex) — an invalid URL will produce a `ConnectionError` on the first POST, which is caught and converts to `crm-logged-notify-pending`. This matches the spec's FR-009 edge-case ruling.

**Rationale**: Format validation of URLs is brittle and adds complexity without catching the most common real-world error (wrong URL path, revoked webhook). The fail-fast check on empty/None catches the "not configured" case at startup; everything else is caught at delivery time.

---

## Summary of Implementation Constraints

| Constraint | Value | Source |
|-----------|-------|--------|
| Discord rate limit | 30 req / 60 s per webhook | Discord API docs |
| 429 `retry_after` | float seconds in response body JSON | Discord API docs |
| Embed title max | 256 chars (HTTP 400 if exceeded) | Discord API docs |
| Embed description max | 4096 chars | Discord API docs |
| Field value max | 1024 chars | Discord API docs |
| Total embed max | 6000 chars | Discord API docs |
| HTTP idempotency key | None — each POST creates new message | Discord API docs |
| requests timeout form | `(connect_s, read_s)` | requests docs |
| Connect timeout | 5 s | Decision 5 |
| Read timeout | 10 s | Decision 5 |
| Protocol style | `typing.Protocol` | Decision 4 |
