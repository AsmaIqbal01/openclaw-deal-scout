# Data Model: Gmail Intake & Deal Detection

**Branch**: `001-gmail-intake` | **Date**: 2026-07-09
**Source**: Key Entities section in `spec.md`, refined in `plan.md`

All entities are implemented as Python `dataclasses` in `src/gmail_intake/models.py`.

---

## DealPayload

The structured output produced for each confirmed deal. Returned in `deals_extracted[]` in the tool response.

```python
from dataclasses import dataclass
from typing import Optional, Literal

@dataclass
class DealPayload:
    gmail_message_id:  str                          # Required; non-empty; idempotency key
    sender_email:      str                          # Required; must contain '@'
    sender_name:       Optional[str]                # Optional; null if absent from From header
    subject:           str                          # Required; non-empty
    received_at:       str                          # Required; "YYYY-MM-DDTHH:MM:SSZ" from internalDate
    deal_summary:      str                          # Required; 1–2 sentences; max 500 chars (FR-011)
    deal_category:     Literal[
                           "lead",
                           "partnership_inquiry",
                           "vendor_offer",
                           "rfq",
                           "other"
                       ]                            # Required; exactly one enum value
    confidence_score:  float                        # Required; 0.0–1.0 inclusive
    raw_email_excerpt: Optional[str]                # Optional; max 500 chars; null if body absent
```

### Field population sources

| Field | Populated from | Before or after classifier call |
|---|---|---|
| `gmail_message_id` | Gmail API `id` field | Before |
| `sender_email` | Gmail `From` header (address portion) | Before |
| `sender_name` | Gmail `From` header (display name portion, if present) | Before |
| `subject` | Gmail `Subject` header | Before |
| `received_at` | Gmail `internalDate` (Unix epoch ms → ISO 8601 UTC) | Before |
| `deal_summary` | Classifier JSON response | After |
| `deal_category` | Classifier JSON response | After |
| `confidence_score` | Classifier JSON response | After |
| `raw_email_excerpt` | Classifier JSON response | After |

### Validation rules (enforced in `extractor.py`)

| Field | Rule | Failure outcome |
|---|---|---|
| `gmail_message_id` | Non-empty string | `invalid_metadata` (should never happen — Gmail always provides id) |
| `sender_email` | Non-empty; must contain `@` | `invalid_metadata` |
| `subject` | Non-empty | `invalid_metadata` |
| `received_at` | Non-empty; `internalDate` must be non-zero numeric string | `invalid_metadata` |
| `deal_summary` | Non-empty; truncated to 2 sentences then 500 chars (FR-011) | `schema_error` if classifier returns null |
| `deal_category` | Must be one of the 5 enum values | `schema_error` |
| `confidence_score` | 0.0 ≤ value ≤ 1.0 | `schema_error` |
| `raw_email_excerpt` | If present, max 500 chars at word boundary | Truncated; never `schema_error` |

---

## ProcessedMessage

One entry per email evaluated by the tool. Written to the `messages` array in the state store.

```python
from typing import Literal

@dataclass
class ProcessedMessage:
    gmail_message_id: str
    processed_at:     str       # ISO 8601 UTC; timestamp of completed atomic write
    outcome:          Literal[
                          "deal_extracted",
                          "not_a_deal",
                          "schema_error",
                          "rate_limited",
                          "body_absent",
                          "invalid_metadata",
                          "classification_error"
                      ]
```

### Outcome enum semantics

| Outcome | Trigger condition | DealPayload produced? |
|---|---|---|
| `deal_extracted` | `is_deal=true` AND `confidence_score ≥ 0.5` AND all required fields valid | Yes |
| `not_a_deal` | `is_deal=false` OR `confidence_score < 0.5` | No |
| `schema_error` | Classifier JSON missing a required field, or field fails type/range validation | No |
| `rate_limited` | Gemini 429 with all 3 retries exhausted | No |
| `body_absent` | Email body is absent or empty (attachment-only emails) | No |
| `invalid_metadata` | `internalDate` absent/zero/non-numeric, or `From` header absent/invalid, or `Subject` absent/empty | No |
| `classification_error` | Any non-429 Gemini error, or unhandled per-message exception | No |

Note: `auth_failure` is a cycle-level event, not a per-message event. No message ID is ever assigned this outcome.

---

## ClassificationRequest

The 5-field input sent to the Gemini classifier for each email (after pre-flight validation).

```python
@dataclass
class ClassificationRequest:
    subject:          str
    sender_email:     str
    sender_name:      Optional[str]   # null if not present in From header
    body_excerpt:     Optional[str]   # email body capped at 8,000 chars; null if body absent
    target_segment:   str = "UK micro-business, fewer than 10 employees"
```

The classifier is never called when `body_excerpt` is null (body-absent case is caught before classification, per FR-018 / edge case "attachment-only email").

---

## ClassificationResponse

The JSON schema that Gemini MUST return. Enforced via `response_schema` in `GenerationConfig` (see `research.md` Decision 6).

```python
@dataclass
class ClassificationResponse:
    is_deal:           bool
    confidence_score:  float             # 0.0–1.0
    deal_category:     Optional[Literal[
                           "lead",
                           "partnership_inquiry",
                           "vendor_offer",
                           "rfq",
                           "other"
                       ]]                # null when is_deal=false
    deal_summary:      Optional[str]     # null when is_deal=false
    raw_email_excerpt: Optional[str]     # null when is_deal=false; max 500 chars
```

All five fields are always present in the Gemini response (Gemini enforces the schema). Null values indicate a non-deal classification.

---

## StateStore

The top-level structure of `processed_ids.json`.

```python
from dataclasses import field

@dataclass
class StateStore:
    last_poll_time: Optional[str]          # ISO 8601 UTC | null on first run
    messages:       list[ProcessedMessage] = field(default_factory=list)
```

### JSON on-disk representation

```json
{
  "last_poll_time": "2026-07-09T14:30:00Z",
  "messages": [
    {
      "gmail_message_id": "18f3a4b2c1d0e5f6",
      "processed_at": "2026-07-09T14:30:01Z",
      "outcome": "deal_extracted"
    },
    {
      "gmail_message_id": "18f3a4b2c1d0e5f7",
      "processed_at": "2026-07-09T14:30:02Z",
      "outcome": "not_a_deal"
    }
  ]
}
```

### State Store lifecycle rules

| Condition | Behaviour |
|---|---|
| File does not exist | Normal first-run state; 24-hour lookback window applied (FR-002) |
| File exists, `last_poll_time = null` | Treat as first run; 24-hour lookback (FR-002) |
| File exists, `last_poll_time` is valid ISO 8601 | Use as poll start timestamp |
| File exists, `last_poll_time` is malformed / non-ISO | Treat as null; log WARN; continue (never fatal) |
| File exists but cannot be read (permission denied, invalid JSON at top level) | Log ERROR, suspend cycle (fatal startup error per spec) |
| File write fails (disk full, permission denied) | Log ERROR, skip recording that message ID; continue processing remaining messages |
| File size > 50 MB | Log WARN once per cycle; write proceeds normally |

### Serialisation helpers

```python
import dataclasses, json

def store_to_dict(store: StateStore) -> dict:
    return dataclasses.asdict(store)

def dict_to_store(d: dict) -> StateStore:
    messages = [ProcessedMessage(**m) for m in d.get("messages", [])]
    return StateStore(
        last_poll_time=d.get("last_poll_time"),
        messages=messages
    )
```

---

## Entity Relationships

```
Gmail API
    │
    ▼
[Gmail message] ──(headers)──► ClassificationRequest
                                        │
                                        ▼
                                 Gemini 2.5 Flash
                                        │
                                        ▼
                               ClassificationResponse
                                        │
                               ┌────────┴──────────┐
                           is_deal=true          is_deal=false
                           conf ≥ 0.5            or conf < 0.5
                               │                       │
                               ▼                       ▼
                          DealPayload         ProcessedMessage
                          (returned)          outcome=not_a_deal
                               │
                               ▼
                       ProcessedMessage
                       outcome=deal_extracted
                               │
                               ▼
                          StateStore
                         (persisted to
                      processed_ids.json)
```
