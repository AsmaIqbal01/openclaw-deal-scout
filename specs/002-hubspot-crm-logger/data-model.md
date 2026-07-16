# Data Model: HubSpot CRM Logger

**Branch**: `002-hubspot-crm-logger` | **Date**: 2026-07-16
**Source**: Key Entities section in `spec.md`, refined in `plan.md` and `research.md`

All new entities are Python `dataclasses` in `src/crm_logger/models.py`.
Cross-feature changes to `src/gmail_intake/models.py` and `state_store.py` are noted explicitly.

---

## CrmStateStore

The extended top-level structure of `processed_ids.json`, adding the 401-cycle counter.

```python
from dataclasses import dataclass, field

@dataclass
class CrmStateStore:
    last_poll_time:          str | None          # ISO 8601 UTC | None on first run
    consecutive_401_cycles:  int                 # Default 0 if absent from JSON
    messages:                list[dict]          # Raw message dicts (not typed — see CrmMessage)
```

**On-disk JSON** (extended from 001's format):
```json
{
  "last_poll_time": "2026-07-16T10:00:00Z",
  "consecutive_401_cycles": 0,
  "messages": [
    {
      "gmail_message_id": "abc123",
      "processed_at": "2026-07-16T10:01:00Z",
      "outcome": "crm-pending",
      "sender_email": "vendor@example.com",
      "sender_name": "Vendor Corp",
      "subject": "Partnership Proposal",
      "received_at": "2026-07-16T09:55:00Z",
      "deal_summary": "Vendor Corp proposes a distribution partnership.",
      "deal_category": "partnership_inquiry",
      "confidence_score": 0.92,
      "raw_email_excerpt": "We are interested in partnering with your firm..."
    },
    {
      "gmail_message_id": "def456",
      "processed_at": "2026-07-16T10:02:00Z",
      "outcome": "crm-logged",
      "sender_email": "buyer@example.com",
      "sender_name": "Buyer Ltd",
      "subject": "RFQ: Office Supplies",
      "received_at": "2026-07-16T09:58:00Z",
      "deal_summary": "Buyer Ltd requests a quote for office supplies.",
      "deal_category": "rfq",
      "confidence_score": 0.88,
      "raw_email_excerpt": "Please send us a quote for 500 units..."
    }
  ]
}
```

**Backward compatibility**: 001's `read_store()` ignores `consecutive_401_cycles` (not referenced) and ignores extra message fields (only picks `gmail_message_id`, `processed_at`, `outcome` by explicit key). No change to 001's `read_store()` logic is required.

---

## CrmMessage

A raw message dict from the state store that carries a complete DealPayload. Used by `crm_logger/state_store.py` — read as dicts, not via the `ProcessedMessage` constructor.

**Fields present for `deal_extracted`, `crm-pending`, and `crm-logged` entries**:

| Field | Type | Source |
|---|---|---|
| `gmail_message_id` | `str` | DealPayload; primary key |
| `processed_at` | `str` (ISO-8601 UTC) | Written by 001 on first write; updated by 002 on transition |
| `outcome` | `str` | `deal_extracted` \| `crm-pending` \| `crm-logged` |
| `sender_email` | `str` | DealPayload |
| `sender_name` | `str \| None` | DealPayload |
| `subject` | `str` | DealPayload |
| `received_at` | `str` (ISO-8601 UTC) | DealPayload |
| `deal_summary` | `str` | DealPayload |
| `deal_category` | `str` (enum) | DealPayload |
| `confidence_score` | `float` | DealPayload |
| `raw_email_excerpt` | `str \| None` | DealPayload |

**Entries with other outcomes** (`not_a_deal`, `schema_error`, etc.) carry only the 3 base fields and do NOT include the 9 payload fields.

---

## HubSpotContact

What the CRM Logger reads from / writes to HubSpot for a contact record.

```python
@dataclass
class HubSpotContact:
    hubspot_id:   str         # HubSpot internal contact ID (from search or create response)
    email:        str         # sender_email
    firstname:    str         # first token of sender_name (empty string if name absent)
    lastname:     str         # remaining tokens of sender_name (empty string if no space in name)
```

**Name-split rule** (FR-014):
```
sender_name = "Jane Doe Smith"  →  firstname="Jane",  lastname="Doe Smith"
sender_name = "Alice"           →  firstname="Alice", lastname=""
sender_name = None / ""         →  firstname="",      lastname=""
```

Implementation:
```python
def split_name(sender_name: str | None) -> tuple[str, str]:
    if not sender_name:
        return ("", "")
    parts = sender_name.split(" ", maxsplit=1)
    return (parts[0], parts[1] if len(parts) > 1 else "")
```

---

## HubSpotDeal

What the CRM Logger writes to HubSpot for a deal record.

```python
@dataclass
class HubSpotDeal:
    hubspot_id:                 str     # HubSpot internal deal ID (from create response)
    dealname:                   str     # subject, truncated per FR-004
    openclaw_deal_category:     str     # DealCategory enum value
    openclaw_confidence_score:  float   # 0.0–1.0
    openclaw_deal_summary:      str     # deal_summary (full, untruncated)
    openclaw_received_date:     int     # received_at as Unix epoch milliseconds
    openclaw_gmail_message_id:  str     # gmail_message_id
```

**Deal name truncation** (FR-004):
```python
def truncate_dealname(subject: str) -> str:
    if len(subject) <= 255:
        return subject
    return subject[:252] + "..."
```

**Date conversion** (Decision 6):
```python
from datetime import datetime

def to_epoch_ms(iso_str: str) -> int:
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)
```

**HubSpot API property keys**:

| Python field | HubSpot property key | Property type | Pre-created? |
|---|---|---|---|
| `dealname` | `dealname` | Standard (built-in) | Yes |
| `openclaw_deal_category` | `openclaw_deal_category` | Custom — single-line text | Must create |
| `openclaw_confidence_score` | `openclaw_confidence_score` | Custom — decimal number | Must create |
| `openclaw_deal_summary` | `openclaw_deal_summary` | Custom — multi-line text | Must create |
| `openclaw_received_date` | `openclaw_received_date` | Custom — date (epoch ms) | Must create |
| `openclaw_gmail_message_id` | `openclaw_gmail_message_id` | Custom — single-line text | Must create |

All 5 `openclaw_*` properties must be created in HubSpot before first run (one-time setup, see `quickstart.md`).

---

## HubSpotWriteResult

The outcome of a single `log_deal()` call, returned internally from `HubSpotClient`.

```python
from typing import Literal

@dataclass
class HubSpotWriteResult:
    outcome:      Literal["crm-logged", "crm-pending", "skipped"]
    hubspot_deal_id:  str | None    # Set when outcome == "crm-logged"
    error_reason:     str | None    # Set when outcome == "crm-pending"
```

---

## Exceptions (src/crm_logger/models.py)

```python
class HubSpot401Error(Exception):
    """HubSpot returned 401 Unauthorized — credential invalid."""

class HubSpotRateLimitError(Exception):
    """HubSpot returned 429 Too Many Requests."""

class HubSpotResponseError(Exception):
    """HubSpot returned a non-success status (non-401, non-429)."""

class HubSpotMissingResourceIdError(Exception):
    """HubSpot returned 200 but response body missing expected resource ID."""

class CrmStateStoreReadError(Exception):
    """CRM state store cannot be read or parsed."""
```

---

## New Outcome Values (cross-feature change to gmail_intake/models.py)

`ProcessedMessageOutcome` in `src/gmail_intake/models.py` must be extended to include the two new CRM outcomes:

```python
ProcessedMessageOutcome = Literal[
    "deal_extracted",
    "not_a_deal",
    "schema_error",
    "rate_limited",
    "body_absent",
    "invalid_metadata",
    "classification_error",
    "crm-pending",     # NEW — CRM write failed; eligible for retry
    "crm-logged",      # NEW — CRM write confirmed by HubSpot
]
```

These values appear in the `outcome` field of message entries written by 002. 001's code never writes them, but 001's `read_store()` will encounter them in JSON and must not raise. Since `ProcessedMessage.outcome` is a `Literal` type annotation (not a runtime validator), adding them to the Literal is a documentation change, not a runtime change — 001's existing code already handles unknown outcome values silently.

---

## State Transitions

```
001 writes:
  [unread Gmail email]
       │
       ▼
  deal_extracted  ◄── 9 DealPayload fields stored alongside 3 base fields (FR-015)
       │
       │  (002 reads deal_extracted entries; reconstructs DealPayload from JSON)
       │
       ▼
  ┌─── HubSpot write ───┐
  │                     │
  ▼ (success + ID)      ▼ (any failure)
crm-logged          crm-pending
                        │
                        │  (FR-008: retried next cycle before new deals)
                        │
               ┌────────┴────────┐
               │                 │
               ▼ (retry OK)      ▼ (retry fails again)
          crm-logged         crm-pending
                               (stays pending; WARN logged)
```

**ConsecutiveAuthFailureCounter state machine**:
```
consecutive_401_cycles = 0 (default / post-recovery)
       │
       │ [401 response in cycle AND no successes in same cycle]
       ▼
consecutive_401_cycles += 1
       │
       │ [reaches 3]
       ▼
SUSPENDED (FATAL log; all CRM writes blocked)
       │
       │ [operator restarts agent]
       ▼
consecutive_401_cycles reset to 0 (WARN log)
       │
       │ [next successful HubSpot response]  [next 401]
       ├──────────────────────────────────►  counter stays 0 (success resets)
       │
       └──────────────────────────────────►  counter increments (new suspension sequence begins)
```

---

## Cross-Feature Changes to 001 (gmail_intake)

### `src/gmail_intake/state_store.py`

1. **`_atomic_write()`** — adopt merge-write to preserve unknown top-level keys:
   ```python
   def _atomic_write(path: str, store: StateStore, extra_msg_fields: dict[str, dict] | None = None) -> None:
       # Read existing JSON to preserve top-level keys written by other modules (e.g., consecutive_401_cycles)
       existing: dict = {}
       if os.path.exists(path):
           try:
               with open(path, "r", encoding="utf-8") as fh:
                   existing = json.load(fh)
           except (OSError, json.JSONDecodeError):
               pass

       messages = []
       for m in store.messages:
           entry = dataclasses.asdict(m)
           if extra_msg_fields and m.gmail_message_id in extra_msg_fields:
               entry.update(extra_msg_fields[m.gmail_message_id])
           messages.append(entry)

       payload = {
           **existing,                          # preserve consecutive_401_cycles etc.
           "last_poll_time": store.last_poll_time,
           "messages": messages,
       }
       # ... atomic write via tempfile + os.replace (unchanged)
   ```

2. **`append_message()`** — add `extra_fields` parameter:
   ```python
   def append_message(
       path: str,
       store: StateStore,
       entry: ProcessedMessage,
       extra_fields: dict | None = None,
   ) -> None:
       store.messages.append(entry)
       extra_msg_fields = {entry.gmail_message_id: extra_fields} if extra_fields else None
       _atomic_write(path, store, extra_msg_fields)
   ```

### `src/gmail_intake/server.py`

When appending a `deal_extracted` entry, pass the 9 DealPayload fields as `extra_fields`:
```python
append_message(
    state_path,
    store,
    ProcessedMessage(
        gmail_message_id=payload.gmail_message_id,
        processed_at=now_utc(),
        outcome="deal_extracted",
    ),
    extra_fields={
        "sender_email": payload.sender_email,
        "sender_name": payload.sender_name,
        "subject": payload.subject,
        "received_at": payload.received_at,
        "deal_summary": payload.deal_summary,
        "deal_category": payload.deal_category,
        "confidence_score": payload.confidence_score,
        "raw_email_excerpt": payload.raw_email_excerpt,
    },
)
```

---

## CrmCycleResult

The structured return value from `orchestrator.run_crm_cycle()`, forwarded as the `sync_deals_to_crm` tool response.

```python
@dataclass
class CrmCycleResult:
    status:        str           # "ok" | "error"
    crm_logged:    int           # deals successfully written this cycle
    crm_pending:   int           # deals in crm-pending state at cycle end
    skipped:       int           # deals already crm-logged (idempotency skip)
    suspended:     bool          # True if consecutive_401_cycles >= 3
    error_details: str | None    # top-level error message if status == "error"
```
