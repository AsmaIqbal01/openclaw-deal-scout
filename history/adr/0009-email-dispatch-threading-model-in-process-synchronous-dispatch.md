# ADR-0009: Email Dispatch Threading Model — In-Process Synchronous Dispatch

- **Status:** Accepted
- **Date:** 2026-07-26
- **Feature:** 007-email-scheduling

- **Context:** Feature 007 introduces two new write paths against `email_queue.json`:
  (1) the pipeline scheduler thread that runs `schedule_for_deal()` and `dispatch_pending()`
  inside `run_cycle()`, and (2) the asyncio HTTP handlers that process `POST /api/emails/{id}/approve`
  and `POST /api/emails/{id}/cancel` from the gateway event loop. ADR-0005 already established
  that the gateway runs a single process with two concurrent execution contexts: the uvicorn
  event loop (main thread) and a pipeline scheduler thread (daemon thread). Feature 007 must
  fit within that model without introducing a new daemon thread or new systemd unit, while
  also preventing race conditions between the HTTP handlers and the scheduler thread writing
  to the same shared queue state.

  Three concrete questions must be answered:
  1. Does email dispatch run inline in `run_cycle()` (step 4), or in its own background thread?
  2. What concurrency primitive serialises writes to `email_queue.json` from both contexts?
  3. How does the asyncio HTTP handler acquire a blocking lock without stalling Uvicorn's event loop?

## Decision

**Email dispatch runs synchronously inline inside `run_cycle()` step 4**, as two sequential
sub-steps using the existing `ThreadPoolExecutor` thread — no new background thread:

- **Step 4a** — `schedule_for_deal(deal_payload)`: called once per deal in
  `result1["deals_extracted"]`; runs in the same executor thread as steps 1–3.
- **Step 4b** — `dispatch_pending()`: called once per cycle after all step-4a calls, even
  when no new deals were processed; runs in the same executor thread.

**Concurrency primitive**: a single `threading.Lock` instance owned by `EmailQueueStore`.
All write operations (approve, cancel, schedule, dispatch state updates) acquire this lock
before mutating the in-memory queue or writing atomically to disk.

**HTTP handler write path**: asyncio coroutines (`api_approve_email`, `api_cancel_email`)
use `await asyncio.to_thread(store.approve, email_id)` and
`await asyncio.to_thread(store.cancel, email_id)` to offload the lock-acquiring write to the
thread pool, returning the event loop immediately while the thread pool executes the mutation.

**Audit log concurrency**: `AuditLogger` wraps `logging.FileHandler` with `propagate=False`.
Python's `logging` module serialises handler writes with an internal lock — no additional
locking required for audit writes from either context.

**Dispatch latency**: Because dispatch is tied to `run_cycle()`, send latency is bounded by
the pipeline cycle interval (`POLL_INTERVAL_MINUTES`, default 15 minutes). An email approved
at 09:01 on Monday will dispatch at the next cycle tick — at most 15 minutes later. This is
explicitly documented as an accepted constraint (spec Assumptions, FR-006).

Diagram:

```
Main thread (uvicorn event loop)
│
├── POST /api/emails/{id}/approve  ──asyncio.to_thread──►  thread pool
│                                                           └── store.approve()
│                                                               └── threading.Lock
│                                                               └── atomic write to disk
│
└── (uvicorn serves other requests)

Daemon thread (pipeline scheduler loop — from ADR-0005)
│
└── run_cycle()  (via run_in_executor — NEW executor thread per cycle)
    ├── step 1: gmail_intake
    ├── step 2: crm_logger
    ├── step 3: discord_notifier
    ├── step 4a: schedule_for_deal() × N  ──► threading.Lock  ──► atomic write
    └── step 4b: dispatch_pending()        ──► threading.Lock  ──► atomic write
                                               ──► Gmail API send
```

## Consequences

### Positive

- **No new threads or processes**: The entire email scheduling and dispatch capability runs
  within the existing two-context model from ADR-0005. No new systemd unit, no new daemon
  thread, no new executor pool.
- **Simple lock model**: A single `threading.Lock` covers all write paths. No deadlock risk
  from nested locks; no starvation because lock hold time is bounded by one atomic file write
  (~1 ms on local disk).
- **Event loop never blocked**: `asyncio.to_thread()` ensures the uvicorn event loop is
  non-blocking even when the queue write queues behind an ongoing cycle write. Other HTTP
  requests continue to be served during the wait.
- **Predictable dispatch timing**: Dispatch is tied to the cycle interval — behaviour is
  deterministic and auditable from `pipeline.log`. No background thread waking up at arbitrary times.
- **Consistent error handling**: Step 4 errors follow the same `try/except → errors.append()`
  pattern as steps 1–3. A Gmail API failure in `dispatch_pending()` never terminates the cycle.

### Negative

- **Dispatch latency up to 15 minutes**: An email approved immediately after a cycle completes
  will wait up to `POLL_INTERVAL_MINUTES` before dispatch. Operators who expect near-instant
  send after approval will be surprised. This is a deliberate v1 tradeoff documented in the spec.
- **Cycle duration increases**: Each call to `dispatch_pending()` makes one Gmail API request
  per eligible email. On a large queue, this could extend the cycle duration significantly.
  At <20 emails/day the impact is negligible (<1 s per email), but if volume grows this
  decision should be revisited.
- **Lock contention possible under concurrent load**: If an HTTP handler and the scheduler
  thread attempt a write simultaneously, one blocks on `threading.Lock` acquisition. The
  blocked party is always the HTTP handler (via `asyncio.to_thread()`), which holds up that
  specific API response but not the event loop. Under normal single-operator conditions,
  this is invisible; under artificial concurrent load it could produce slightly elevated
  approve/cancel API latency.
- **`asyncio.to_thread()` requires Python 3.9+**: The project already targets Python 3.12,
  so this is not a practical constraint, but it is a hidden floor if the runtime ever needs
  to run on an older Python.

## Alternatives Considered

### Alternative A — Dedicated background dispatch thread (runs independently of pipeline cycle)

A new `threading.Thread(daemon=True)` wakes on a shorter interval (e.g., every 5 minutes)
and calls `dispatch_pending()` independently of `run_cycle()`.

**Tradeoffs**:
- **Pro**: Lower dispatch latency — approved emails could be sent within 5 minutes regardless
  of pipeline cycle timing.
- **Con**: Introduces a third concurrent execution context not present in ADR-0005, requiring
  a new `threading.Event` for shutdown coordination, a new lock interaction with the cycle
  thread, and new test infrastructure for the background thread lifecycle.
- **Con**: `dispatch_pending()` would need its own lock strategy with `run_cycle()` step 4
  to prevent double-dispatch of the same email.
- **Con**: Increases process complexity for a single-operator, low-volume use case.

**Rejected**: Dispatch latency of ≤15 minutes is explicitly acceptable to the operator (spec
Assumptions). The added complexity of a third thread is not justified by the marginal latency
improvement.

### Alternative B — asyncio.Lock instead of threading.Lock

Use `asyncio.Lock` for all write serialisation; schedule thread acquires it via
`asyncio.run_coroutine_threadsafe(lock.acquire(), loop)`.

**Tradeoffs**:
- **Pro**: Keeps all locking in the asyncio domain; conceptually uniform with the event loop.
- **Con**: `asyncio.run_coroutine_threadsafe()` from the executor thread requires holding a
  reference to the event loop, making the `EmailQueueStore` aware of the asyncio infrastructure.
  This couples the store to the runtime context (gateway-hosted vs. standalone, test vs. prod).
- **Con**: More complex to test: unit tests for the store must create an event loop; teardown
  must cancel the coroutine.

**Rejected**: `threading.Lock` + `asyncio.to_thread()` keeps the `EmailQueueStore` runtime-agnostic.
The store has no knowledge of the event loop; it is just a thread-safe in-memory data structure.

### Alternative C — Per-request file reads (no in-memory store; no lock)

HTTP handlers read `email_queue.json` from disk on every request; the scheduler also reads
fresh from disk on every cycle step. Each write uses atomic rename. No shared in-memory state,
no lock needed (each read sees the most recent committed state).

**Tradeoffs**:
- **Pro**: No in-memory state means no risk of staleness; no lock means no contention.
- **Con**: Every `GET /api/emails` triggers a disk read. Under dashboard auto-refresh (every
  60 s), this generates constant I/O with no benefit, since the queue rarely changes.
- **Con**: A write race between the scheduler and an HTTP handler could occur between the read
  and the write of an approve operation (time-of-check to time-of-use). Atomic rename prevents
  file corruption but does not prevent the HTTP handler from approving based on stale state
  that the scheduler has already advanced.
- **Con**: No atomic read-modify-write without a lock; a concurrent approve + dispatch could
  produce an inconsistent queue file.

**Rejected**: The in-memory store + lock is strictly safer. I/O benefit of Alternative C is
marginal at <20 emails/day. The TOCTOU race condition is a hard correctness problem.

## References

- Feature Spec: `specs/007-email-scheduling/spec.md` (FR-013, Assumptions — threading.Lock)
- Implementation Plan: `specs/007-email-scheduling/plan.md` (Decisions 4, 5, 6)
- Research: `specs/007-email-scheduling/research.md` (R-003, R-004, R-005)
- Related ADRs: ADR-0005 (gateway single-process two-context model — this ADR extends it)
- Related ADRs: ADR-0008 (Gmail API send — the dispatch sub-step uses this send mechanism)
- PHR: `history/prompts/007-email-scheduling/0002-email-scheduling-plan-007.plan.prompt.md`
