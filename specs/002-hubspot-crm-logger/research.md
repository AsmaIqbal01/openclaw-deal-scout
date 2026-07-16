# Phase 0 Research: HubSpot CRM Logger

**Branch**: `002-hubspot-crm-logger` | **Date**: 2026-07-16
**Resolves**: All technical unknowns in `plan.md` Technical Context

---

## Decision 1 — HubSpot API Client Strategy

**Decision**: Direct REST calls via `requests` library (no official `hubspot-api-client` SDK)

**Rationale**:
- Only 4 endpoint types are needed: contact search, contact upsert, deal create, deal-contact association
- `hubspot-api-client` (official Python SDK, v8+) adds ~40 MB of generated code and 15+ transitive dependencies for 4 simple HTTP calls
- Direct `requests` calls make the 100ms inter-call delay (FR-006) explicit and trivially testable — the delay is a `time.sleep(0.1)` inside a single `_call()` method that every endpoint goes through
- `requests` is a transitive dependency already present in the virtualenv; no new package pinning required

**Alternatives considered**:
- `hubspot-api-client` SDK: full type safety and auto-generated endpoint methods. Rejected — overkill for 4 calls; delay injection at per-call granularity is less obvious with generated methods; 15+ extra transitive deps violates "smallest viable diff" principle.
- `httpx` (async): async HTTP client with identical API surface to requests. Rejected — the CRM module is synchronous Python; adding an asyncio event loop for 4 sequential calls adds complexity without benefit.

---

## Decision 2 — HubSpot API Endpoints (v3/v4)

**Decision**: v3 for object CRUD; v4 for associations

| Operation | Method | Endpoint |
|---|---|---|
| Contact search by email | POST | `/crm/v3/objects/contacts/search` |
| Contact create | POST | `/crm/v3/objects/contacts` |
| Deal create | POST | `/crm/v3/objects/deals` |
| Deal-to-contact association | PUT | `/crm/v4/associations/deals/contacts/batch/create` |

**Rationale**: v3 is stable and fully supported on HubSpot Free tier for contact/deal CRUD. v4 associations is the current recommended approach; the v3 per-object association endpoint (`/crm/v3/objects/deals/{id}/associations/contacts/{id}/{type}`) is still functional but the v4 batch form is cleaner and avoids the deprecated per-object pattern. All 4 endpoints return a resource `id` on success — satisfies FR-009 (must validate resource ID in response).

**Request body references**:

Contact search:
```json
{
  "filterGroups": [{
    "filters": [{"propertyName": "email", "operator": "EQ", "value": "<sender_email>"}]
  }],
  "properties": ["email", "firstname", "lastname", "hs_object_id", "createdate"],
  "limit": 10
}
```

Contact create:
```json
{"properties": {"email": "<email>", "firstname": "<first>", "lastname": "<rest>"}}
```

Deal create:
```json
{
  "properties": {
    "dealname": "<subject, truncated per FR-004>",
    "openclaw_deal_category": "<deal_category>",
    "openclaw_confidence_score": <float>,
    "openclaw_deal_summary": "<deal_summary>",
    "openclaw_received_date": <unix_epoch_ms>,
    "openclaw_gmail_message_id": "<gmail_message_id>"
  }
}
```

Deal-to-contact association:
```json
{
  "inputs": [{
    "from": {"id": "<deal_id>"},
    "to": {"id": "<contact_id>"},
    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]
  }]
}
```
(`associationTypeId: 3` = "deal to contact" in HubSpot's predefined association type registry)

---

## Decision 3 — 100ms Inter-Call Delay Implementation

**Decision**: `time.sleep(0.1)` at the end of `HubSpotClient._call()`, applied unconditionally after every non-401 response

**Rationale**:
- Single enforcement point: all 4 API methods route through `_call()`. The delay cannot be accidentally skipped.
- Post-response placement: the delay follows the response, so the first call in a cycle starts immediately. For N sequential calls, total inter-call sleep = N × 100ms — exactly FR-006's intent.
- `time.sleep` is appropriate for synchronous code (no event loop to block).
- On 401: the delay is NOT applied because `_call()` raises `HubSpot401Error` before reaching the sleep line — no further calls are made in that cycle per FR-007.

**Alternatives considered**:
- Token bucket / leaky bucket: supports burst semantics. Rejected — Constitution Principle VI specifies a fixed 100ms minimum delay; no burst allowance is permitted.
- Per-call sleep in each endpoint method: invites omission bugs. Rejected in favor of centralized enforcement.

---

## Decision 4 — State Store Extension Strategy (FR-015)

**Decision**: Two-layer backward-compatible approach

**Layer 1 — 001 write path (targeted change)**:
Update `gmail_intake/state_store.py`:
- `_atomic_write()`: adopt a merge-write pattern — read the existing JSON file before writing and merge in updated fields, so unknown top-level keys (e.g., `consecutive_401_cycles`) written by 002 are preserved.
- `append_message()`: add an optional `extra_fields: dict | None = None` parameter; when non-None, merge these fields into the message dict before writing. The `server.py` call site passes the 9 DealPayload fields for `deal_extracted` entries.

**Layer 2 — 002 read path**:
`crm_logger/state_store.py` reads the JSON file as raw dicts (bypassing `ProcessedMessage` constructor) to access all 9 payload fields and the `consecutive_401_cycles` top-level counter. Writes use the same merge-write pattern.

**Why backward compatible**:
- 001's `read_store()` picks only 3 explicit fields per message (`m["gmail_message_id"]`, `m["processed_at"]`, `m["outcome"]`) — not `ProcessedMessage(**m)`. Extra fields are silently ignored.
- 001's `read_store()` calls `raw.get("last_poll_time")` and `raw.get("messages", [])` — all other top-level keys are silently ignored, so `consecutive_401_cycles` does not break 001.

**Alternatives considered**:
- Separate `crm_state.json` file: two files = two locks = risk of inconsistency (entry present in one file but not the other). Rejected.
- Add Optional fields to `ProcessedMessage` dataclass in 001: pollutes 001's data model with 002's concerns. Rejected.
- SQLite with separate tables: violates the constitution's file-based JSON mandate for this MVP. Rejected.

---

## Decision 5 — Module Structure

**Decision**: New Python package `src/crm_logger/` with 6 modules

| Module | Responsibility |
|---|---|
| `models.py` | Dataclasses: `CrmStateStore`, `CrmMessage`, `HubSpotContact`, `HubSpotDeal`, `HubSpotWriteResult`, exceptions |
| `client.py` | `HubSpotClient` — 4 API methods + centralized `_call()` with 100ms delay + per-cycle call counter |
| `state_store.py` | CRM state operations: raw JSON read, write `crm-pending`/`crm-logged`, read/write `consecutive_401_cycles` |
| `log_deal.py` | `log_deal(payload, client, state_path) -> Literal["crm-logged", "crm-pending", "skipped"]` |
| `orchestrator.py` | `run_crm_cycle(state_path, token) -> CrmCycleResult` — drain pending + process new + 401 counter management |
| `server.py` | FastMCP server exposing `sync_deals_to_crm` MCP tool |

**Rationale**: Mirrors `gmail_intake` structure exactly. `log_deal` is isolated and unit-testable with a mocked `HubSpotClient`. `orchestrator.py` is the only module that touches cycle-level state (401 counter, per-cycle call counter).

---

## Decision 6 — HubSpot Date Property Format

**Decision**: Convert `received_at` (ISO-8601 UTC string) → Unix epoch milliseconds (integer) for `openclaw_received_date`

```python
from datetime import datetime

def to_epoch_ms(iso_str: str) -> int:
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)
```

**Rationale**: HubSpot date and datetime properties are stored as Unix milliseconds since epoch (UTC). Python 3.11+ handles ISO-8601 strings via `fromisoformat()`. The conversion is a one-liner; no additional library needed.

---

## Decision 7 — MCP Tool Interface

**Decision**: Zero-parameter tool `sync_deals_to_crm` in `src/crm_logger/server.py`

**Rationale**: Consistent with `check_new_deals` (zero parameters; reads all state from the shared store). OpenClaw calls `check_new_deals` then `sync_deals_to_crm` in sequence each poll cycle.

**Tool response schema**:
```json
{
  "status": "ok | error",
  "crm_logged": <int>,
  "crm_pending": <int>,
  "skipped": <int>,
  "suspended": <bool>,
  "error_details": "<string | null>"
}
```

**OpenClaw MCP config addition**:
```json
{
  "mcpServers": {
    "crm-logger": {
      "command": "python",
      "args": ["-m", "crm_logger.server"],
      "cwd": "/home/asmaiqbal01/openclaw-deal-scout",
      "env": {
        "HUBSPOT_PRIVATE_APP_TOKEN": "${HUBSPOT_PRIVATE_APP_TOKEN}",
        "STATE_STORE_PATH": "${STATE_STORE_PATH}"
      }
    }
  }
}
```

---

## Decision 8 — Contact Dedup: Multi-Match Resolution

**Decision**: When contact search returns multiple results for the same email, select the contact with the numerically smallest `id` value

```python
contacts = response_json["results"]
if len(contacts) > 1:
    logger.warning("multiple HubSpot contacts for %s: %s", sender_email, [c["id"] for c in contacts])
    contact = min(contacts, key=lambda c: int(c["id"]))
else:
    contact = contacts[0]
```

**Rationale**: HubSpot internal IDs are monotonically increasing integers — the lowest ID is the earliest-created contact. The spec (edge case section) specifies "earliest HubSpot creation date (lowest internal ID)". ID comparison is simpler than parsing `createdate` and is equivalent.

---

## Decision 9 — `log_deal` Suspension Bypass (FR-007)

**Decision**: `run_crm_cycle()` in `orchestrator.py` checks `consecutive_401_cycles` before calling `log_deal` for any deal; when suspended, emits a single INFO log and returns immediately without invoking `log_deal` at all

**Rationale**: The spec (FR-007 suspension behavior) says FR-008 state-store inspection is bypassed entirely during suspension — meaning `log_deal` is never called, and no deal state transitions occur. Implementing the bypass in `orchestrator.py` (not inside `log_deal`) keeps `log_deal` pure — it never needs to know about suspension, which simplifies unit testing.

**Recovery on restart**: `run_crm_cycle()` reads `consecutive_401_cycles` on startup; if ≥ 3, logs the WARN message and resets to 0 before the first cycle runs (per FR-007 recovery semantics).
