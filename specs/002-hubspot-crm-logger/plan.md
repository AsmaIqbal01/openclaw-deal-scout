# Implementation Plan: HubSpot CRM Logger

**Branch**: `002-hubspot-crm-logger` | **Date**: 2026-07-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/002-hubspot-crm-logger/spec.md`

---

## Summary

A new Python package `src/crm_logger/` extends the pipeline by reading confirmed deals from the shared JSON state store (`processed_ids.json`) and writing them to HubSpot Free CRM via direct REST calls. Each poll cycle: drain `crm-pending` entries first → process new `deal_extracted` entries → 100ms delay between every HubSpot API call → track 401 cycles and suspend all writes after 3 consecutive failing cycles. The CRM Logger Module (`log_deal`) is exposed as a zero-parameter MCP tool `sync_deals_to_crm`, called by OpenClaw after `check_new_deals`. A targeted change to `001-gmail-intake`'s state store write path persists all 9 DealPayload fields alongside `deal_extracted` entries so the CRM logger can reconstruct full payloads on retry without re-querying Gmail.

---

## Technical Context

**Language/Version**: Python 3.11+ (same as `001-gmail-intake`)

**Primary Dependencies**:
- `fastmcp ≥2.0` — MCP server framework; `@mcp.tool()` decorator (already installed)
- `requests ≥2.31` — HubSpot REST API calls (v3/v4 endpoints); new dependency
- `portalocker ≥2.8` — state store file lock (already installed)
- `python-dotenv ≥1.0` — environment variable loading (already installed)

**Storage**: Shared `processed_ids.json` state store, extended with:
- `consecutive_401_cycles` top-level integer key (default 0)
- 9 DealPayload fields on `deal_extracted`, `crm-pending`, `crm-logged` message entries

**Testing**: `pytest ≥8.0`; unit tests mock `HubSpotClient` and state store; integration tests use a HubSpot sandbox account

**Target Platform**: Linux (Ubuntu 22.04 on WSL, systemd-managed headless service)

**Project Type**: Single Python package extension (`src/crm_logger/` sibling to `src/gmail_intake/`)

**Performance Goals**: ≤3 s per deal at 100ms inter-call spacing; 90 calls/cycle max ≈ 30 deals/cycle; ~150 HubSpot calls/day at expected workload (well under 250,000/day free-tier limit)

**Constraints**:
- HubSpot Free burst limit: 100 requests/10s per private app (FR-006)
- 100ms mandatory inter-call delay between sequential HubSpot API calls (FR-006, Constitution Principle VI)
- 90-call-per-cycle circuit breaker (FR-011)
- No paid APIs, no cloud infrastructure (Constitution I)
- State store file-based JSON (no SQLite, no Redis)
- `HUBSPOT_PRIVATE_APP_TOKEN` in `.env` only — never committed

**Scale/Scope**: Single HubSpot Free account; ≤50 confirmed deals/day; 3 API calls/deal; well within all free-tier limits

---

## Constitution Check

*Constitution v1.0.1 — evaluated pre-implementation.*

| # | Gate | Verdict | Reason |
|---|---|---|---|
| 1 | Paid dependency introduced? | ✅ PASS | `requests` (Apache 2.0, free); `fastmcp` (MIT); HubSpot Free CRM — no credit card, no paid tier, no cloud infrastructure bill |
| 2 | Non-Gmail intake source added? | ✅ PASS | Reads DealPayload data from the shared state store written by `001-gmail-intake`; no new intake channel introduced |
| 3 | Runtime browser login required? | ✅ PASS | Static private-app Service Key token read from `HUBSPOT_PRIVATE_APP_TOKEN` env var; no OAuth flow, no browser prompt at runtime (FR-005) |
| 4 | Risk of duplicate CRM entries or alerts? | ✅ CONDITIONAL PASS | FR-002 (idempotency gate by Gmail message ID) + FR-003 (contact dedup by email) prevent duplicates under normal operation. FR-013 documents one acknowledged exception: if the state-store write to `crm-logged` fails after a confirmed HubSpot write, the deal remains `crm-pending` and a duplicate deal record may be created on the next retry cycle. This risk is bounded and has a defined manual recovery path. |
| 5 | Core pipeline modified for new notifier? | ⬜ N/A | This is CRM logging, not a notifier adapter. The notifier architecture (feature 003) is unaffected. The only change to 001 is the state store write path for FR-015 (persisting 9 DealPayload fields for `deal_extracted` entries). |
| 6 | Exception can crash agent process? | ✅ PASS | FR-007 catches all HubSpot write failures as `crm-pending`; `HubSpot401Error` is propagated to `orchestrator.py` where it triggers `crm-pending` for the remaining cycle deals and counter increment — no unhandled raise; SC-007 (no crash, no halt) enforced at the tool boundary in `server.py` |

**Overall**: ✅ PASS (1 N/A) — cleared for implementation

---

## Project Structure

### Documentation (this feature)

```text
specs/002-hubspot-crm-logger/
├── plan.md                       # This file
├── research.md                   # Phase 0 — API strategy, delay impl, state store extension
├── data-model.md                 # Phase 1 — Python dataclasses and state schema
├── quickstart.md                 # Phase 1 — HubSpot setup, custom properties, env, first run
├── contracts/
│   └── crm-logger-contract.md   # Phase 1 — MCP tool and log_deal() contracts
└── tasks.md                      # Phase 2 — /sp.tasks output (not yet created)
```

### Source Code (repository root)

```text
src/
├── gmail_intake/                 # Existing (001) — targeted changes only
│   ├── models.py                 # Extend ProcessedMessageOutcome with "crm-pending", "crm-logged"
│   ├── state_store.py            # Update _atomic_write (merge-write); update append_message (extra_fields)
│   └── server.py                 # Pass 9 DealPayload fields as extra_fields for deal_extracted entries
└── crm_logger/                   # New (002)
    ├── __init__.py
    ├── models.py                 # CrmStateStore, CrmMessage, HubSpotContact, HubSpotDeal,
    │                             #   HubSpotWriteResult, CrmCycleResult, exceptions
    ├── client.py                 # HubSpotClient — 4 API methods, _call() with 100ms delay,
    │                             #   per-cycle call counter
    ├── state_store.py            # CRM state read/write: raw JSON, outcome transitions,
    │                             #   consecutive_401_cycles
    ├── log_deal.py               # log_deal(payload, client, state_path)
    │                             #   -> Literal["crm-logged", "crm-pending", "skipped"]
    ├── orchestrator.py           # run_crm_cycle(state_path, token) -> CrmCycleResult
    │                             #   drain pending + process new + 401 counter management
    └── server.py                 # FastMCP server; sync_deals_to_crm tool

tests/
├── unit/
│   ├── test_hubspot_client.py    # _call() delay, 401 raise, 429 raise, multi-contact dedup
│   ├── test_log_deal.py          # FR-002 skip, FR-004 truncation, FR-014 name split,
│   │                             #   invalid_sender_email edge case
│   ├── test_orchestrator.py      # FR-007 401 counter, FR-008 drain order, FR-011 circuit
│   │                             #   breaker (31 deals → 30 written + 1 deferred)
│   └── test_crm_state_store.py   # read/write with 9 payload fields, consecutive_401_cycles
└── integration/
    └── test_sync_deals_to_crm.py # End-to-end against HubSpot sandbox account
```

**Structure Decision**: Single project (`src/`), consistent with `001-gmail-intake`. New `crm_logger` package is a direct sibling — no monorepo split, no new virtualenv, no new `pyproject.toml` section. The existing `pyproject.toml` / `requirements.txt` gains one new entry: `requests`.

---

## Implementation Phases

### Phase 1 — New `crm_logger` package (no dependencies on 001 changes)

Build the standalone CRM logger module. All tests in this phase use mocked state store and mocked `HubSpotClient`.

1. `src/crm_logger/models.py` — dataclasses and exceptions
2. `src/crm_logger/client.py` — `HubSpotClient` with `_call()`, 100ms delay, per-cycle counter
3. `src/crm_logger/state_store.py` — raw JSON read/write, `consecutive_401_cycles`
4. `src/crm_logger/log_deal.py` — `log_deal()` with FR-002 gate, FR-004 truncation, FR-014 name split
5. `src/crm_logger/orchestrator.py` — `run_crm_cycle()` with FR-007 401 logic, FR-008 drain order, FR-011 circuit breaker
6. `src/crm_logger/server.py` — FastMCP tool wrapping `run_crm_cycle()`
7. Unit tests for all modules

### Phase 2 — Cross-feature changes to `001-gmail-intake` (FR-015 dependency)

Targeted changes to persist the 9 DealPayload fields for `deal_extracted` entries.

1. `src/gmail_intake/models.py` — extend `ProcessedMessageOutcome` Literal
2. `src/gmail_intake/state_store.py` — merge-write in `_atomic_write()`; `extra_fields` param in `append_message()`
3. `src/gmail_intake/server.py` — pass 9 DealPayload fields via `extra_fields` for `deal_extracted` entries
4. Update `tests/unit/test_state_store.py` — cover merge-write and extra_fields behaviour

### Phase 3 — Integration

1. `tests/integration/test_sync_deals_to_crm.py` — end-to-end test against HubSpot sandbox
2. OpenClaw MCP config updated (see `quickstart.md`)

---

## Key Architectural Decisions (cross-references to research.md)

| Decision | Summary | Research ref |
|---|---|---|
| HubSpot API client | `requests` library; direct REST; no official SDK | Decision 1 |
| API endpoints | v3 for CRUD; association embedded in deal create body | Decision 2 |
| 100ms delay | `time.sleep(0.1)` in `_call()` after every non-401 response | Decision 3 |
| State store extension | Merge-write in 001; raw JSON reads in 002 | Decision 4 |
| Module structure | 6-module `crm_logger` package | Decision 5 |
| Date property format | `received_at` → Unix epoch milliseconds via `datetime.fromisoformat()` | Decision 6 |
| MCP tool | Zero-param `sync_deals_to_crm`; OpenClaw calls after `check_new_deals` | Decision 7 |
| Contact dedup | Lowest HubSpot ID on multi-match | Decision 8 |
| Suspension bypass | Checked in `orchestrator.py` before calling `log_deal` | Decision 9 |

---

## Complexity Tracking

No Constitution Check violations detected. This section is not required.
