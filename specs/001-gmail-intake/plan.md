# Implementation Plan: Gmail Intake & Deal Detection

**Branch**: `001-gmail-intake` | **Date**: 2026-07-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-gmail-intake/spec.md`

---

## Summary

A Python FastMCP server exposes a single zero-parameter MCP tool `check_new_deals`.
On each invocation: acquire exclusive lock on the JSON state store → poll Gmail for
unread messages since last successful poll → classify each via Gemini 2.5 Flash
(structured JSON mode) → extract and validate a DealPayload for every confirmed deal
→ atomically write each ProcessedMessage to the state store → release lock → return
a typed result dict to the OpenClaw caller. OpenClaw (Node.js agent gateway) connects
to this server via stdio MCP transport.

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**:
- `fastmcp ≥2.0` — MCP server framework; `@mcp.tool()` decorator pattern
- `google-api-python-client ≥2.130` — Gmail API client
- `google-auth-oauthlib ≥1.2` + `google-auth-httplib2 ≥0.2` — OAuth offline flow
- `google-generativeai ≥0.8` — Gemini 2.5 Flash; `response_mime_type="application/json"` for structured output
- `portalocker ≥2.8` — cross-platform exclusive file locking (satisfies FR-003b)

**Storage**: File-based JSON (`processed_ids.json`) — zero infrastructure, human-readable, survives reboots without a daemon

**Testing**: `pytest ≥8.0` + `pytest-asyncio`; unit tests mock Gmail and Gemini clients; integration tests use a sandbox Gmail account with VCR cassettes for Gemini responses

**Target Platform**: Linux (Ubuntu 22.04 on WSL, intended for systemd-managed headless service)

**Project Type**: Single Python package (`src/gmail_intake/`)

**Performance Goals**: ≤30 s per 50-message poll cycle. Gemini 2.5 Flash p95 latency ≈ 100–500 ms/call sequential. Worst case: 50 × 500 ms = 25 s plus network overhead.

**Constraints**:
- Free-tier only — no paid APIs, no cloud infra
- Gemini 2.5 Flash free quota: ~15 requests/min; plan retry schedule accounts for this
- State store disk: warn at 50 MB threshold (spec FR-015 note)
- No persistent background threads — invocation model is stateless per call except for the file lock

**Scale/Scope**: Single Gmail inbox; 50 emails/poll cap (configurable); ~18,000 state entries/year; ~2.7 MB/year state store growth

---

## Constitution Check

*Constitution v1.0.1 — evaluated pre-implementation.*

| # | Gate | Verdict | Reason |
|---|---|---|---|
| 1 | Paid dependency introduced? | ✅ PASS | All free: Gmail API (free quota), Gemini 2.5 Flash (free tier), FastMCP (MIT), google-api-python-client (Apache 2.0), portalocker (MIT) |
| 2 | Non-Gmail intake source added? | ✅ PASS | Gmail API only; no scraping, RSS, or webhooks anywhere in scope |
| 3 | Runtime browser login required? | ✅ PASS | OAuth offline token + programmatic refresh via `google.auth.transport.requests.Request()`; initial one-time setup is a separate offline step (see quickstart.md) |
| 4 | Risk of duplicate CRM entries or alerts? | ✅ PASS | No CRM or notification calls in this step; exclusive file lock + atomic per-message writes prevent duplicate state entries (FR-003b, FR-013) |
| 5 | Core pipeline modified for new notifier? | ⬜ N/A | This is the Gmail intake step; no notification adapter code is present or referenced |
| 6 | Exception can crash agent process? | ✅ PASS | Per-message catch-all at FR-020; cycle-level errors return `status: "error"` without raising; FastMCP tool exceptions are caught and returned as structured error responses |

**Overall**: ✅ PASS (1 N/A) — cleared for implementation

---

## Project Structure

### Documentation (this feature)

```text
specs/001-gmail-intake/
├── plan.md              # This file
├── research.md          # Phase 0 — tech decisions, classifier prompt, FR-011 regex
├── data-model.md        # Phase 1 — Python dataclasses and state schema
├── quickstart.md        # Phase 1 — setup, OAuth init, first run, testing
├── contracts/
│   └── tool-contract.md # Phase 1 — MCP tool interface contract
└── tasks.md             # Phase 2 — /sp.tasks output (not yet created)
```

### Source Code

```text
src/
└── gmail_intake/
    ├── __init__.py
    ├── server.py          # FastMCP server; registers and exposes check_new_deals
    ├── gmail_client.py    # Gmail API: auth, programmatic token refresh, inbox polling
    ├── classifier.py      # Gemini 2.5 Flash: classify() with retry + exponential backoff
    ├── extractor.py       # DealPayload extraction: FR-011 sentence rule, 500-char caps
    ├── state_store.py     # JSON state store: lock(), read(), append(), update_poll_time()
    └── models.py          # Dataclasses: DealPayload, ProcessedMessage, ClassificationResponse

tests/
├── unit/
│   ├── test_classifier.py      # Retry logic, non-429 error handling, JSON parsing
│   ├── test_extractor.py       # FR-011 sentence truncation, 500-char cap, field validation
│   └── test_state_store.py     # Atomic write, lock conflict, read failure, 50 MB warn
├── integration/
│   └── test_check_new_deals.py # End-to-end: seeded sandbox inbox → invoke → verify state
└── contract/
    └── test_tool_contract.py   # Return shape and types match Tool Contract exactly

data/
└── .gitkeep                    # Committed empty; processed_ids.json is gitignored

.env.example                    # Required env vars (committed, placeholder values)
.env                            # Actual values (gitignored — NEVER committed)
pyproject.toml                  # Package metadata, dependencies, pytest config
```

**Structure decision**: Single Python package under `src/gmail_intake/`. Six modules mirror the six processing phases (auth → poll → classify → extract → persist → return). Tests in three layers: unit (mocked), integration (live sandbox), contract (schema conformance). The `data/` directory is committed empty via `.gitkeep`; the state store file itself is gitignored.

---

## Module Responsibilities

### `models.py`
Defines all shared data contracts as Python dataclasses:
- `DealPayload` — 9-field typed output per confirmed deal
- `ProcessedMessage` — state store entry per processed email
- `ClassificationRequest` — inputs to the Gemini classifier
- `ClassificationResponse` — Gemini JSON output schema
- `StateStore` — top-level `processed_ids.json` structure

See `data-model.md` for full field definitions.

### `state_store.py`
Single responsibility: safe, atomic, idempotent reads and writes to `processed_ids.json`.

Key operations:
- `acquire_lock(path)` — `portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)` for FR-003b concurrent-invocation detection; raises `LockError` if already held
- `read_store(path)` — deserialise JSON; raise `StateStoreReadError` on any read/parse failure (FR spec: fatal startup error, never silent fallback)
- `append_message(path, entry)` — write to `{path}.tmp`, then `os.rename()` (POSIX atomic); on write failure log ERROR and continue (FR spec: acceptable duplication risk)
- `update_poll_time(path, ts)` — same atomic write pattern; called only after a non-fatal poll cycle completes

### `gmail_client.py`
Encapsulates all Gmail API interactions:
- `build_service(credentials_path)` — load credentials JSON; call `google.auth.transport.requests.Request()` for programmatic token refresh; raise `AuthError` on refresh failure
- `poll_inbox(service, since_ts, max_messages)` — Gmail `users.messages.list` with `q="after:{epoch}"` filter; sort by `internalDate` ascending; cap at `max_messages`; parse headers (`From`, `Subject`, `internalDate`)
- Token refresh: one attempt only (FR-016); on success continue; on failure raise `AuthError`

Environment variable consumed: `GMAIL_CREDENTIALS_PATH`

### `classifier.py`
Wraps the Gemini 2.5 Flash API with retry logic:
- `classify(request: ClassificationRequest) -> ClassificationResponse` — sends the classifier prompt (see `research.md`) with `response_mime_type="application/json"`; validates response JSON against `ClassificationResponse` schema
- Retry: 1 initial + 3 retries for HTTP 429, with delays 10 s / 30 s / 60 s (FR-007)
- Non-429 errors (400, 500, 503, connection refused, timeout): per-message WARN log, `classification_error` outcome, no retry (FR-021)
- `response_schema` passed to Gemini to enforce structured output (eliminates manual JSON parsing)

### `extractor.py`
Stateless field extraction and validation:
- `extract_payload(msg_headers, classification) -> DealPayload` — maps Gmail headers + ClassificationResponse to DealPayload; validates all required fields
- `truncate_summary(text: str) -> str` — applies FR-011: sentence-boundary rule first (regex defined in `research.md`), then 500-char hard cap
- `truncate_excerpt(text: str) -> str` — truncates at nearest word boundary at or before 500 chars (FR-010)
- Raises `SchemaValidationError` for any required-field violation; caller records `schema_error` outcome

### `server.py`
FastMCP server entry point:
```python
from fastmcp import FastMCP
mcp = FastMCP("gmail-intake")

@mcp.tool()
async def check_new_deals() -> dict:
    ...  # orchestrates all modules; returns Tool Contract dict
```
- Reads env vars at call time (not at import), so the server can start before `.env` is fully populated in tests
- All exceptions at the tool boundary are caught; returns `{"status": "error", ...}` never raises

---

## Key Implementation Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Runtime language | Python 3.11+ | FastMCP is Python-native; Google APIs have mature Python SDKs; Gemini structured-output feature is best-supported in Python |
| MCP transport | stdio | Zero network config; OpenClaw spawns the server as a subprocess; no port management needed on the operator's machine |
| File lock mechanism | `portalocker` | Cross-platform (works on WSL + native Linux); LOCK_NB raises immediately on contention rather than blocking; explicit `LockError` for clean FR-003b handling |
| Atomic write | `tempfile` + `os.rename()` | POSIX atomic rename; zero external dependency; crash between writes leaves only committed entries, satisfying FR-013 partial-write recovery |
| Gemini JSON mode | `response_mime_type="application/json"` + `response_schema` | Gemini enforces schema at the API level; eliminates brittle regex-based JSON extraction from prose responses |
| State store format | JSON (not SQLite) | Zero infra; human-readable for debugging; no migration tooling needed; 2.7 MB/year growth is manageable without a DB |
| FR-011 sentence boundary | Regex with title-abbreviation exclusion list | Deterministic, testable, no NLP dependency; see `research.md` for the exact regex |

---

## Error Handling Matrix

| Failure | Module | Action | State store outcome |
|---|---|---|---|
| `GMAIL_CREDENTIALS_PATH` absent | `server.py` | Log ERROR, return `status: "error"` | Not written (no message ID) |
| State store unreadable | `state_store.py` | Log ERROR, return `status: "error"` | Not written |
| Concurrent invocation (lock held) | `state_store.py` | Log WARN, return `status: "error"`, `error_details: "concurrent invocation"` | Not written |
| Gmail auth/token expiry, refresh fails | `gmail_client.py` | Log ERROR, return `status: "error"` | Not written (`last_poll_time` not advanced) |
| Gmail rate limit | `gmail_client.py` | Log WARN, abort cycle | Not written; `last_poll_time` not advanced |
| Network failure mid-poll | `gmail_client.py` | Log WARN, abort cycle | Entries already written are retained |
| Invalid `internalDate` | `extractor.py` | Log WARN, continue | `invalid_metadata` |
| Invalid / missing `From` or `Subject` | `extractor.py` | Log WARN, continue | `invalid_metadata` |
| Body absent / empty | `extractor.py` | Log INFO, continue | `body_absent` |
| Gemini 429 (retries exhausted) | `classifier.py` | Log WARN, continue | `rate_limited` |
| Gemini non-429 error | `classifier.py` | Log WARN, continue (no retry) | `classification_error` |
| Gemini JSON schema violation | `classifier.py` | Log WARN, continue | `schema_error` |
| `is_deal=false` or `confidence<0.5` | `classifier.py` | Log INFO, continue | `not_a_deal` |
| Unhandled per-message exception | `server.py` | Log ERROR + stack trace, continue | `classification_error` |
| State store write failure | `state_store.py` | Log ERROR, continue (message re-evaluated next run) | Not written (duplication risk accepted) |
| State store >50 MB | `state_store.py` | Log WARN once per cycle | Normal write proceeds |

