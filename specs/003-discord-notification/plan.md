# Implementation Plan: Discord Deal Notification

**Branch**: `003-discord-notification` | **Date**: 2026-07-17 | **Spec**: [spec.md](spec.md)

## Summary

Introduces `src/discord_notifier/` — a new FastMCP server package that reads
`crm-logged` entries from the shared `processed_ids.json` state store and
delivers structured Discord alerts via webhook. Extends the shared state store
with three new per-entry fields (`status` transitions, `notified_at`, `error_reason`)
using the same atomic merge-write pattern established in Steps 1 and 2. No new
Python dependencies, no new state file, no new infrastructure.

---

## Technical Context

**Language/Version**: Python 3.12 (same as `gmail_intake` and `crm_logger`)
**Primary Dependencies**: `requests>=2.31` (already in pyproject.toml from Step 2),
  `portalocker>=2.8` (already present), `fastmcp>=2.0` (already present) —
  **zero new dependencies required**
**Storage**: `processed_ids.json` — shared file-based JSON state store; extended
  with notification fields on existing message entries; no new file or schema
**Testing**: pytest + pytest-asyncio (already configured in pyproject.toml)
**Target Platform**: Linux / systemd (same self-hosted deployment as Steps 1 and 2)
**Project Type**: Single Python project (follows existing `src/` layout)
**Performance Goals**: Idempotency check completes in < 10 ms (no I/O); per-call
  Discord HTTP timeout = (5 s connect, 10 s read); no cycle-level rate-cap logic
  required (Discord handles per-webhook backpressure via 429 with `retry_after`)
**Constraints**: Zero new infrastructure cost; remains within Discord's free-tier
  webhook rate limit (30 requests/60-second window per webhook); no new Python
  packages; state store file must remain backward-compatible with Steps 1 and 2

---

## Constitution Check

| Gate | Question | Answer | Evidence |
|------|----------|--------|---------|
| I | Does this introduce a paid dependency? | **No** | Discord webhooks: free, no credit card; zero new packages |
| II | Does this add a non-Gmail intake source? | **No** | Reads from state store only; no new intake channel |
| III | Does this require a runtime browser login? | **No** | `DISCORD_WEBHOOK_URL` is a static env var credential |
| IV | Does this risk duplicate notifications? | **No** | Idempotency guard in `notify_deal()` checks `status == "discord-notified"` before any API call |
| V | Does this modify core pipeline files to add a notifier? | **No** | Notifier lives in `discord_notifier/adapter.py`; selected via `NOTIFIER` env var factory |
| VI | Does this allow an exception to crash the agent? | **No** | Per-deal exception boundary in `run_notify_cycle()`; pending state on all failure paths |

**All six gates PASS. No constitution violations.**

---

## Architecture Decisions

### Decision 1: Discord Webhook over Bot Token

- **Chosen**: Webhook URL (static credential, zero bot setup)
- **Rationale**: Webhook requires only a URL copied from Discord channel settings.
  No OAuth, no bot permissions, no guild invite flow. Satisfies Principle III.
- **Alternative rejected**: Discord bot token — requires bot app registration,
  guild membership, and a runtime API call to resolve channel ID. More complex
  with no additional capability needed for the MVP alert use case.

### Decision 2: `typing.Protocol` for NotifierContract

- **Chosen**: Structural subtyping via `typing.Protocol`
- **Rationale**: Test fakes and the `NoopAdapter` do not need to import the
  Protocol class to satisfy the contract. Avoids coupling test files to adapter
  internals. `DiscordAdapter` and `NoopAdapter` are independently testable in
  isolation.
- **Alternative rejected**: `abc.ABC` — requires explicit inheritance, couples
  all adapters to a shared base class import, and offers no runtime benefit over
  Protocol for this use case.

### Decision 3: Extend Shared State Store, Not a New File

- **Chosen**: Write notification fields (`status`, `notified_at`, `error_reason`)
  directly onto existing `processed_ids.json` message entries using the same
  `_merge_write` pattern established in `crm_logger/state_store.py`
- **Rationale**: A single source of truth for deal lifecycle state. Steps 1, 2,
  and 3 all cooperate on the same JSON file without requiring schema migrations
  or file synchronisation. Allows the orchestrator to read the full deal lifecycle
  in one file read.
- **Alternative rejected**: Separate `notifications.json` — adds a second file
  to manage, increases the risk of consistency drift between CRM state and
  notification state, and requires a join operation to reconstruct deal history.

### Decision 4: Drain-First Ordering (Pending Before New)

- **Chosen**: `get_pending_notifications()` (status=`crm-logged-notify-pending`)
  processed before `get_ready_to_notify()` (status=`crm-logged`) each cycle
- **Rationale**: Consistent with `crm_logger`'s drain-first pattern. Prevents
  pending entries from aging unboundedly while new entries are processed first.
- **No retries within a single cycle**: A 429 or failure leaves the deal pending;
  the next scheduled cycle drains it.

### Decision 5: No Retry Counter Field

- **Chosen**: No `retry_count` field; indefinite retry each cycle
- **Rationale**: Complexity of a retry counter (threshold logic, terminal state,
  extra schema field) outweighs benefit for a webhook that fails due to external
  misconfiguration. An `[ERROR]` log on each failed attempt is the escalation
  mechanism. The operator resolves the webhook URL and retries naturally.
- **Revisit condition**: If the operator reports accumulation of stale pending
  entries after a long webhook outage, add a `notify-failed` terminal state
  via a constitution amendment.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-discord-notification/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   ├── sync_notifications.tool.md
│   └── discord_adapter.interface.md
└── checklists/
    └── requirements.md
```

### Source Code

```text
src/discord_notifier/
├── __init__.py                  # empty package marker
├── models.py                    # DiscordWebhookError, DiscordRateLimitError,
│                                #   DiscordTimeoutError, NotifyOutcome (Literal),
│                                #   NotificationCycleResult (dataclass)
├── adapter.py                   # NotifierContract (Protocol), DiscordAdapter,
│                                #   NoopAdapter, get_adapter() factory
├── formatter.py                 # format_embed(deal: dict) -> dict
│                                #   (title truncation, null sender_name, field mapping)
├── state_store.py               # read_notify_store(), get_ready_to_notify(),
│                                #   get_pending_notifications(), write_notify_outcome()
├── notifier.py                  # notify_deal(deal, adapter, state_path) -> NotifyOutcome
│                                #   (idempotency guard + state write)
├── orchestrator.py              # run_notify_cycle(state_path, notifier_name,
│                                #   webhook_url) -> NotificationCycleResult
└── server.py                    # FastMCP server, sync_notifications tool

tests/unit/
├── test_discord_adapter.py      # DiscordAdapter: HTTP 2xx, 4xx, 429, 5xx, timeout
├── test_notify_formatter.py     # format_embed: null name, empty summary, truncation
├── test_notify_state_store.py   # read, filter by status, write outcome (merge-write)
├── test_notifier.py             # notify_deal: idempotency, success, failure paths
└── test_notify_orchestrator.py  # drain-first, cycle result, missing NOTIFIER

tests/integration/
└── test_sync_notifications.py   # real Discord webhook (requires DISCORD_WEBHOOK_URL)
```

**Structure Decision**: Single project extending existing `src/` layout. No new
build targets, no new entry points beyond the FastMCP `server.py`. Same
`setuptools.find` auto-discovery picks up `discord_notifier` automatically.

---

## State Transition Model

Deal lifecycle in `processed_ids.json` (all status values, all three steps):

```
gmail_intake writes:
  → "deal_extracted"       (deal found, not yet CRM-logged)
  → "not_a_deal"           (terminal; skipped)
  → "body_absent"          (terminal; skipped)
  → "invalid_metadata"     (terminal; skipped)
  → "rate_limited"         (terminal; skipped)
  → "classification_error" (terminal; skipped)
  → "schema_error"         (terminal; skipped)

crm_logger writes:
  "deal_extracted" → "crm-logged"          (CRM write succeeded)
  "deal_extracted" → "crm-pending"         (CRM write failed; retryable)
  "crm-pending"    → "crm-logged"          (retry succeeded)
  "crm-pending"    → "crm-pending"         (retry failed again)

discord_notifier writes:
  "crm-logged"              → "discord-notified"          (delivery confirmed)
  "crm-logged"              → "crm-logged-notify-pending" (delivery failed)
  "crm-logged-notify-pending" → "discord-notified"        (retry succeeded)
  "crm-logged-notify-pending" → "crm-logged-notify-pending" (retry failed again)
```

Terminal states: `discord-notified`, `not_a_deal`, `body_absent`,
`invalid_metadata`, `rate_limited`, `classification_error`, `schema_error`.

---

## Interface Contracts

### MCP Tool: `sync_notifications`

Exposed by `server.py`. Called by the orchestrator (no parameters; all config
from environment).

```
Input:  (none)
Output: {
  "status":           "ok" | "error",
  "discord_notified": int,
  "notify_pending":   int,
  "skipped":          int,
  "error_details":    str | null
}
```

Environment variables read:
- `NOTIFIER` — required; "discord" | "noop"; fails fast if absent/unknown
- `DISCORD_WEBHOOK_URL` — required when NOTIFIER=discord
- `STATE_STORE_PATH` — optional; defaults to `"processed_ids.json"`

### NotifierContract (Protocol)

```python
class NotifierContract(Protocol):
    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]:
        ...
```

Implementations: `DiscordAdapter`, `NoopAdapter`.

### DiscordAdapter

```python
class DiscordAdapter:
    def __init__(self, webhook_url: str, timeout: int = 10) -> None: ...
    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]: ...
```

- Calls `formatter.format_embed(deal)` to build payload
- HTTP POST to `webhook_url` with `timeout=10` (combined connect+read)
- HTTP 2xx → returns `"discord-notified"`
- HTTP 429 → raises `DiscordRateLimitError`
- Connect/read timeout (10 s) → raises `DiscordTimeoutError`
- All other HTTP errors → raises `DiscordWebhookError(status_code, body)`
- All exceptions caught in `notify_deal()` → outcome `"crm-logged-notify-pending"`

---

## Non-Functional Requirements

| Concern | Requirement | Source |
|---------|-------------|--------|
| Cost | Zero new paid services or packages | Constitution I |
| Rate limit | Stay within Discord's 30 req/60 s per-webhook window; 429 → pending (no within-cycle retry) | Constitution VI |
| Idempotency | Status check before every API call; no duplicate sends | Constitution IV |
| Headless | Static webhook URL in `.env`; no interactive auth | Constitution III |
| Observability | DEBUG (cycle start/end), INFO (notified, skipped), WARN (pending), ERROR (unhandled/write-fail) | Constitution VI |
| Secret management | `DISCORD_WEBHOOK_URL` in `.env` only; never committed | CLAUDE.md |
| Test isolation | `DiscordAdapter` fully mockable via `NotifierContract` protocol; unit tests never call real Discord | Step 2 pattern |

---

## Dependencies Map

```
003-discord-notification reads from:
  ← processed_ids.json entries written by 001-gmail-intake (deal_extracted fields)
  ← processed_ids.json entries written by 002-crm-logger  (status = crm-logged)

003-discord-notification writes to:
  → processed_ids.json (status, notified_at, error_reason fields on existing entries)

Backward compatibility:
  001-gmail-intake reads only its own fields; extra fields are silently ignored
  002-crm-logger reads only crm_logger fields; notification fields are ignored
  003-discord-notification reads all fields using raw JSON access (same as Step 2)
```

No changes required to `gmail_intake/` or `crm_logger/` source files.

---

## Complexity Tracking

No constitution violations. No complexity justifications required.
