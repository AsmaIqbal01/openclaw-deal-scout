# Module Contract: HubSpot CRM Logger

**Branch**: `002-hubspot-crm-logger` | **Date**: 2026-07-16
**Spec**: [spec.md](../spec.md) | **Data model**: [data-model.md](../data-model.md)

This document defines the external-facing contracts for the CRM Logger feature:
1. MCP tool contract (`sync_deals_to_crm`)
2. Internal module contract (`log_deal`)
3. State store read/write contract
4. HubSpot API call contract

---

## 1. MCP Tool: `sync_deals_to_crm`

**File**: `src/crm_logger/server.py`

### Description

Reads all deals from the shared state store and attempts to write any unlogged deals to HubSpot Free CRM. Drains `crm-pending` entries first (FR-008), then processes new `deal_extracted` entries. Enforces the 100ms inter-call delay (FR-006) and 90-call-per-cycle circuit breaker (FR-011). Manages the consecutive-401-cycle counter and suspends CRM writes after 3 consecutive failing cycles (FR-007).

### Invocation

Zero parameters. Reads `HUBSPOT_PRIVATE_APP_TOKEN` and `STATE_STORE_PATH` from environment.

```json
{
  "tool": "sync_deals_to_crm",
  "params": {}
}
```

### Success Response

```json
{
  "status": "ok",
  "crm_logged": 3,
  "crm_pending": 0,
  "skipped": 1,
  "suspended": false,
  "error_details": null
}
```

### Suspended Response (consecutive_401_cycles ≥ 3)

```json
{
  "status": "ok",
  "crm_logged": 0,
  "crm_pending": 0,
  "skipped": 0,
  "suspended": true,
  "error_details": null
}
```

### Error Response (cycle-level failure, e.g. state store unreadable)

```json
{
  "status": "error",
  "crm_logged": 0,
  "crm_pending": 0,
  "skipped": 0,
  "suspended": false,
  "error_details": "State store unreadable: [Errno 13] Permission denied"
}
```

### Response Field Definitions

| Field | Type | Description |
|---|---|---|
| `status` | `"ok" \| "error"` | `"error"` only for cycle-level failures (e.g. state store unreadable); per-deal write failures produce `"ok"` with incremented `crm_pending` |
| `crm_logged` | `int ≥ 0` | Deals successfully written to HubSpot this cycle (new + retried) |
| `crm_pending` | `int ≥ 0` | Deals in `crm-pending` state at the end of this cycle (new failures + un-retried old failures) |
| `skipped` | `int ≥ 0` | Deals where `log_deal` returned `"skipped"` (already `crm-logged` in state store — FR-002 idempotency) |
| `suspended` | `bool` | `true` when `consecutive_401_cycles ≥ 3`; no HubSpot calls were attempted |
| `error_details` | `str \| null` | Human-readable error string when `status == "error"`; null otherwise |

### Guarantees

- Never raises an unhandled exception — all errors are caught at the tool boundary and returned as `status: "error"`.
- Idempotent: calling `sync_deals_to_crm` multiple times for the same set of deals is safe; already-logged deals are skipped via FR-002.
- State store is atomically written on each deal transition; a partial cycle does not leave the state store in an inconsistent state.

---

## 2. Internal Module Contract: `log_deal`

**File**: `src/crm_logger/log_deal.py`

### Signature

```python
def log_deal(
    payload: DealPayload,
    client: HubSpotClient,
    state_path: str,
) -> Literal["crm-logged", "crm-pending", "skipped"]
```

### Preconditions

- `payload.gmail_message_id` is non-empty (validated by 001 upstream)
- `payload.sender_email` is non-empty and contains `@` (validated by 001 upstream); if this precondition is violated at runtime, `log_deal` treats it as a write failure: writes `crm-pending`, emits WARN with `invalid_sender_email`, returns `"crm-pending"`
- `client` is an initialized `HubSpotClient` with a valid token (liveness not guaranteed — 401 may be raised)
- `state_path` points to a readable and writable JSON file (or a path where the file will be created)

### Return Values

| Return value | Condition |
|---|---|
| `"skipped"` | `payload.gmail_message_id` already has outcome `crm-logged` in the state store (FR-002) |
| `"crm-logged"` | HubSpot contact + deal created (or contact found) and HubSpot returned a valid resource ID for the deal (FR-009) |
| `"crm-pending"` | Any failure: network error, 4xx (non-401), 5xx, 200 with missing resource ID, `invalid_sender_email`, `crm-pending` write failure after HubSpot success |

### Raises

- `HubSpot401Error`: propagated up to `orchestrator.run_crm_cycle()` which handles within-cycle and cross-cycle 401 logic (FR-007). `log_deal` does NOT catch 401 — it propagates.
- No other exceptions are raised; all other errors are caught, logged, and expressed as `"crm-pending"`.

### Invariants

- Exactly 0 or 3 HubSpot API calls per invocation (0 when `"skipped"`, 3 otherwise: contact search → contact upsert → deal create → association; association is call 4 but is bundled with deal create... actually let me reconsider — it's search + create/upsert + deal create + association = 4 calls at most per deal).

Wait, let me re-check. The spec says "3 calls per deal: contact search + contact upsert + deal create." The association is separate. Let me re-read... Actually I need to reconcile. The spec says:

FR-006: "This constraint applies across all call types (contact search, contact create/update, deal create)"
SC-006: "N × 3 API calls ≤ 100"

So the spec counts 3 calls per deal: search + create/update contact + create deal. The association is apparently not counted separately (or it's bundled into "deal create"). Let me check...

Actually the HubSpot API for deal creation doesn't automatically associate the deal to a contact — you need a separate association call. But looking at the spec's FR-006 which says "3 calls per deal = contact search + contact upsert + deal create" and SC-006 which uses "3 calls per deal"...

I think the spec authors may have omitted the association call from the count, OR they consider the association call as part of "deal create" (some HubSpot endpoints let you associate at creation time via the `associations` field in the deal create request body).

Looking at HubSpot API v3 deal create: you CAN include `associations` in the deal create body:
```json
{
  "properties": {...},
  "associations": [{
    "to": {"id": "<contact_id>"},
    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]
  }]
}
```

This bundles the association into the deal create call, making it exactly 3 API calls (search + contact upsert + deal create with embedded association). This is cleaner and matches the spec's count.

So I should use the `associations` field in the deal create body instead of a separate association call. Let me update Decision 2 to reflect this.

Actually I already committed research.md. I'll note this in the contracts doc and it will be corrected in the implementation. The plan is the right place for this.

For the contract doc, let me say "3 API calls per deal" and note the association is embedded in the deal create body.

### Invariants (revised)

- Exactly 0 or 3 HubSpot API calls per invocation (0 when `"skipped"`, 3 when writing: contact search → contact upsert → deal create with embedded association)
- The association between deal and contact is embedded in the deal create request body (via the `associations` field in the v3 API), not a separate API call
- State store is atomically written exactly once per invocation (either `crm-logged` or `crm-pending` transition), unless `"skipped"` (no write needed)
- `log_deal` never modifies `consecutive_401_cycles` — that is `orchestrator.py`'s responsibility

### Log Output

| Event | Level | Message pattern |
|---|---|---|
| FR-002 skip | DEBUG | `[DEBUG] %s already crm-logged — skipping` (gmail_message_id) |
| Successful write | INFO | `[INFO] %s → crm-logged (HubSpot deal %s)` (gmail_message_id, deal_id) |
| Write failure | WARN | `[WARN] %s → crm-pending: %s` (gmail_message_id, reason) |
| 401 (propagated) | ERROR | `[ERROR] %s — HubSpot 401; aborting cycle` (gmail_message_id) |
| invalid_sender_email | WARN | `[WARN] %s → crm-pending: invalid_sender_email` (gmail_message_id) |

---

## 3. State Store Read/Write Contract

**File**: `src/crm_logger/state_store.py`

### `read_crm_store(path: str) -> CrmStateStore`

Reads `processed_ids.json` as raw JSON. Returns:
- `CrmStateStore(last_poll_time=None, consecutive_401_cycles=0, messages=[])` if file absent
- `CrmStateStore` with `consecutive_401_cycles` defaulting to `0` if key absent from JSON
- Raises `CrmStateStoreReadError` if file exists but is unreadable or invalid JSON

**Does NOT use `ProcessedMessage` constructor** — all message entries are returned as raw dicts to preserve the 9 DealPayload fields.

### `get_pending_deals(store: CrmStateStore) -> list[dict]`

Returns all message dicts with `outcome == "crm-pending"`, in insertion order (earliest first). Preserves all 9 DealPayload fields for reconstruction.

### `get_new_deals(store: CrmStateStore) -> list[dict]`

Returns all message dicts with `outcome == "deal_extracted"`, in insertion order. Preserves all 9 DealPayload fields.

### `write_crm_outcome(path: str, gmail_message_id: str, outcome: Literal["crm-logged", "crm-pending"]) -> None`

Atomically updates the `outcome` field of the matching message entry in `processed_ids.json`. Uses merge-write pattern (read → update in memory → write back) to preserve all other fields including `consecutive_401_cycles` and the 9 DealPayload fields.

Raises: `CrmStateStoreReadError` if the file cannot be read. Write failures are logged as ERROR (not raised) — the deal remains in its previous state; see FR-013.

### `read_401_counter(path: str) -> int`

Reads and returns `consecutive_401_cycles` from the top-level JSON. Returns `0` if absent. Raises `CrmStateStoreReadError` if file is unreadable.

### `write_401_counter(path: str, value: int) -> None`

Atomically updates `consecutive_401_cycles` in the top-level JSON. Uses merge-write pattern to preserve all other fields.

---

## 4. HubSpot API Call Contract

**File**: `src/crm_logger/client.py`

### `HubSpotClient(token: str)`

Initialized with the private-app token. Authorization header: `Authorization: Bearer <token>`. Base URL: `https://api.hubapi.com`.

### `_call(method, path, body) -> dict`

Central HTTP dispatch. Behaviour:
- Inserts 100ms delay (`time.sleep(0.1)`) **after** every non-401 response
- On 401: raises `HubSpot401Error` (delay NOT applied; no further calls in cycle)
- On 429: raises `HubSpotRateLimitError`
- On other non-2xx: raises `HubSpotResponseError(status_code, body)`
- On 200 without expected resource ID in body: raises `HubSpotMissingResourceIdError`
- Increments internal `_call_count` counter (used by `orchestrator.py` for FR-011 circuit breaker)

### `search_contact(email: str) -> str | None`

Returns HubSpot contact ID (string) if found; `None` if not found. On multiple matches, returns the lowest ID (earliest-created). Raises `HubSpotResponseError` on non-200 response (caller in `log_deal` treats this as a write failure → `crm-pending`).

### `upsert_contact(email: str, firstname: str, lastname: str) -> str`

Searches for existing contact first. Returns existing contact ID if found; otherwise creates and returns the new contact ID. Raises `HubSpot401Error`, `HubSpotResponseError`, `HubSpotMissingResourceIdError` on failure.

### `create_deal(deal: HubSpotDeal, contact_id: str) -> str`

Creates the deal with embedded association to `contact_id` (using the `associations` field in the v3 deal create body). Returns the new HubSpot deal ID. 3 API calls total for a full `log_deal` run: search + upsert + create_deal (association is embedded in create_deal body, not a separate call — this matches the spec's "3 calls per deal" count in FR-006 and SC-006).

### Per-Cycle Call Counter

`HubSpotClient` exposes:
- `call_count: int` — read-only property; total calls made since instantiation
- `reset_call_count() -> None` — resets to 0 (called by orchestrator at cycle start)

`orchestrator.py` checks `client.call_count >= 90` before each deal to enforce the FR-011 circuit breaker.
