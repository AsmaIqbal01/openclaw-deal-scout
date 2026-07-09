# ADR-0002: JSON File State Store Mechanism

- **Status:** Accepted
- **Date:** 2026-07-09
- **Feature:** gmail-intake (001-gmail-intake); applicable to all future pipeline steps
- **Context:** Every email processed by the pipeline must be tracked by its Gmail message ID
  to prevent duplicate CRM entries and duplicate notifications (Constitution Principle IV).
  The state store must persist across process restarts, survive partial-write crashes,
  handle concurrent invocation attempts, and operate at zero infrastructure cost. The
  store is append-heavy (one entry per email evaluated), read-once-per-cycle, and never
  queried by arbitrary fields. Expected volume: ~50 entries per poll cycle, ~18,000
  entries/year, ~2.7 MB/year growth rate.

## Decision

Use a **flat JSON file** as the persistent state store, with **`portalocker`** for
exclusive locking and **`tempfile` + `os.rename()`** for atomic per-message writes:

- **Format**: JSON flat file (`processed_ids.json`) with schema `{ last_poll_time, messages[] }`
- **Path**: Configurable via `STATE_STORE_PATH` env var; defaults to `./data/processed_ids.json`
- **Concurrency**: `portalocker.LOCK_EX | LOCK_NB` — exclusive non-blocking lock; concurrent
  invocation fails immediately with `status: "error"` (FR-003b)
- **Atomic writes**: Each `ProcessedMessage` entry is written to a `.tmp` file, then
  `os.rename()` atomically replaces the store file (POSIX atomic on same filesystem)
- **Size policy**: Warn at 50 MB; no archival for MVP; unbounded growth accepted
- **Read failure**: Fatal startup error — operator must resolve before next run (no silent
  fallback to fresh state, which would risk reprocessing logged deals)

## Consequences

### Positive

- **Zero infrastructure**: No database daemon, no migration tooling, no schema management.
  Works identically in development, CI, and production on the operator's machine.
- **Human-readable**: The state file can be inspected, edited, and debugged with any text
  editor or `jq`. This is critical for an operator without database tooling.
- **Re-processable by design**: Deleting or editing an entry in `processed_ids.json` allows
  targeted re-processing of a specific email — a first-class operation per Constitution
  Principle IV ("Re-processing MUST be possible by deleting or editing the state entry").
- **Crash-safe**: POSIX atomic rename means either the full new entry is present or the
  previous state is intact — no partial writes visible to readers.
- **Survives reboots**: JSON file persists on disk across process restarts, unlike in-memory
  stores (explicitly prohibited by Constitution Principle IV).
- **Simple backup**: `cp processed_ids.json processed_ids.json.bak` is a full backup.
  No dump/restore tooling needed.

### Negative

- **No query capability**: Looking up a message ID requires a full linear scan of the
  `messages` array in memory. At ~18,000 entries/year this is fast (~1–2 ms in Python),
  but at scale (multi-year, high-volume) it degrades linearly.
- **Whole-file rewrite on every entry**: Each atomic write rewrites the entire JSON file
  (tempfile → rename pattern). At 50 messages/cycle × ~150 bytes/entry = 7.5 KB/cycle —
  negligible now, but at 50 MB the write cost grows.
- **No concurrent reads during write window**: The exclusive lock means no other process
  can read the state during an active poll cycle. Acceptable for single-instance MVP;
  would block any future monitoring/reporting tool that reads the same file.
- **Unbounded growth**: Without archival, the `messages` array grows forever. The 50 MB
  warning threshold provides an operator signal, but no automatic remediation in MVP.
- **No transactions**: If the process is killed between two `os.rename()` calls (multi-entry
  cycle), entries already written are retained; the unwritten entries are re-evaluated on
  the next run. This is the intended crash-recovery behavior, not a bug, but it means the
  store is eventually consistent, not strictly atomic across a full cycle.

## Alternatives Considered

### Alternative A — SQLite database

- **Write strategy**: SQLite WAL mode; `INSERT OR IGNORE` for idempotency
- **Locking**: SQLite's built-in write lock handles concurrency natively
- **Pros**: Efficient indexed lookup by `gmail_message_id`; no whole-file rewrite;
  native support for concurrent readers during writes (WAL mode); well-understood
  migration path as data grows.
- **Rejected because**: Adds a binary SQLite file to the repo; requires the `sqlite3`
  module (standard library, so no extra install, but requires DB initialization logic);
  the store is not human-readable without tooling; "re-processing by editing the state"
  (Constitution Principle IV) requires SQL knowledge rather than a text editor.
  At the current scale (~18,000 rows/year) the performance advantage over a JSON scan
  is negligible. SQLite can be adopted in a future spec when volume warrants it —
  the migration is a well-understood `json → sqlite INSERT` operation.

### Alternative B — In-memory state (Python dict)

- **Model**: `processed_ids: set[str]` held in memory for the lifetime of the FastMCP
  server process
- **Pros**: Fastest possible lookup; no disk I/O; no locking needed within a single process.
- **Rejected because**: Explicitly prohibited by Constitution Principle IV ("in-memory
  state is PROHIBITED"). A process restart loses all state, causing every previously
  processed email to be reprocessed on the next poll cycle — the exact failure mode
  Principle IV is designed to prevent.

### Alternative C — Redis (or another key-value store)

- **Model**: `SADD processed_ids <message_id>` for O(1) membership test
- **Pros**: O(1) lookup; atomic SADD; built-in TTL for automatic expiry; remote-accessible
  for future multi-instance scenarios.
- **Rejected because**: Redis is a paid/self-hosted service; running a Redis daemon on
  the operator's machine violates the Zero Cost Infrastructure principle (Principle I)
  and the "zero infrastructure bill" constraint. The complexity of managing a Redis
  daemon is not justified at the current scale.

### Alternative D — Append-only log file (one line per processed message ID)

- **Model**: Append one `<message_id>\n` line per processed email; read all lines at startup
- **Pros**: True append-only — no whole-file rewrite; simpler crash recovery (partial
  append is incomplete line, easily detected).
- **Rejected because**: Cannot store per-entry metadata (`processed_at`, `outcome`) without
  a custom serialisation format; `last_poll_time` has no natural home in an append-only
  ID list; harder to make human-readable and editable for re-processing use cases.
  The JSON schema cleanly supports all required fields in one file.

## References

- Feature Spec: `specs/001-gmail-intake/spec.md` (State Store Schema, FR-012–FR-015)
- Implementation Plan: `specs/001-gmail-intake/plan.md` (state_store.py module, error handling matrix)
- Research (Decision 4 — File Lock, Decision 5 — Atomic Writes): `specs/001-gmail-intake/research.md`
- Data Model (StateStore dataclass): `specs/001-gmail-intake/data-model.md`
- Related ADRs: ADR-0001 (Python FastMCP Subprocess Runtime)
- Evaluator Evidence: `history/prompts/gmail-intake/003-gmail-intake-implementation-plan.plan.prompt.md`
