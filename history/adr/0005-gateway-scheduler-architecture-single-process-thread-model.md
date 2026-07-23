# ADR-0005: Gateway Scheduler Architecture — Single-Process Thread Model

- **Status:** Accepted
- **Date:** 2026-07-23
- **Feature:** mcp-dashboard (005-mcp-dashboard)
- **Context:** The OpenClaw gateway must do two things concurrently: (1) serve the FastMCP HTTP server on port 18789 so the dashboard and CLI can reach it at any time, and (2) run the 4-step pipeline on a configurable schedule (every N minutes, via `POLL_INTERVAL_MINUTES`). These two concerns must be unified in a single deployable unit — the `openclaw_gateway` process managed by systemd — because (a) the constitution requires zero paid infrastructure (ruling out external schedulers or message queues), (b) the `run_cycle` MCP tool must block until the cycle completes and return the cycle summary synchronously (FR-003), making a fire-and-forget two-process model insufficient, and (c) the operator should not need to manage two systemd services. The decision directly affects process model, threading strategy, systemd unit configuration, and the cycle-lock contract shared with `pipeline_orchestrator`.

## Decision

Run FastMCP HTTP and the pipeline scheduler in **a single process using two concurrent execution contexts**:

- **HTTP server**: FastMCP 3.4.4 HTTP transport (`mcp.run(transport="http", ...)`) runs in the **main thread** via uvicorn/anyio event loop.
- **Scheduler loop**: A `threading.Thread` (daemon=True) runs the pipeline schedule loop — sleep `POLL_INTERVAL_MINUTES`, call `pipeline_orchestrator.runner.run_cycle()`, repeat.
- **Synchronisation**: The existing `CycleLock` (file-based exclusive lock, `pipeline_orchestrator.lock`) is the sole concurrency gate. Both the scheduler thread and the `run_cycle` MCP tool call `run_cycle()` through the same lock; `CycleLockActiveError` causes the second caller to return a `{"busy": true}` response immediately.
- **SIGTERM handling**: Signal registered in main thread; sets a `threading.Event` (`_shutdown_flag`); scheduler thread checks the flag between cycles and exits; FastMCP HTTP server receives SIGTERM via uvicorn and shuts down; `finally` block in `run_cycle()` always releases the lock.
- **Systemd change**: `openclaw.service` switches from `Type=oneshot` to `Type=simple`; `ExecStart` invokes `python -m openclaw_gateway`; `SCHEDULER_MODE=gateway` activates this dual-context mode.

```
Main thread: uvicorn event loop (FastMCP HTTP on :18789)
                │
                ├── MCP tool call: run_cycle()  ─────────────────┐
                │                                                  │
Daemon thread: scheduler loop                                      │
  sleep(POLL_INTERVAL_MINUTES) → run_cycle() ──────────────────── CycleLock
                                                                   │
                                          pipeline_orchestrator.runner.run_cycle()
```

## Consequences

### Positive

- Single process, single systemd service: operator installs and monitors one unit. No second service to manage, restart, or debug.
- `run_cycle` MCP tool blocks synchronously and returns the cycle summary — satisfying FR-003 without polling or callbacks.
- `CycleLock` prevents double-execution across both callers (scheduler thread and MCP tool) without any additional mutex; the file lock is already battle-tested in production (004-pipeline-orchestration).
- Thread is daemon=True: if the main HTTP server exits for any reason, the scheduler thread is automatically cleaned up — no zombie processes.
- Existing `pipeline_orchestrator` package unchanged: the gateway delegates all scheduling logic to `runner.run_cycle()`, not reimplementing it.

### Negative

- Threading introduces shared-state risk: if `run_cycle()` has a hidden side-effect that is not thread-safe, it could manifest as a race condition. Mitigated by the `CycleLock` and the fact that `run_cycle()` does all I/O through file operations protected by `portalocker`.
- A blocking `run_cycle()` in the scheduler thread (e.g., a Gemini 429 retry chain taking 5–10 minutes) holds the thread for the duration. During this time, a dashboard `run_cycle` MCP tool call will receive `{"busy": true}` and show "cycle in progress." This is correct behaviour but may surprise operators if a cycle runs long.
- `threading.Thread` cannot be cancelled mid-cycle. A SIGTERM received while a cycle is in progress waits for the current step to complete (same behaviour as the existing `pipeline_orchestrator` SIGTERM contract — intentional, avoids partial writes).
- The dual-context model is harder to unit-test than a single-threaded design: tests that exercise the scheduler thread must use `threading.Event` synchronisation or mock `time.sleep`.

## Alternatives Considered

**Alternative A: Two processes — gateway HTTP-only + existing systemd timer**
Keep the existing `openclaw.service` (Type=oneshot) and timer unchanged; add a separate gateway HTTP server process that exposes status/deals/quota MCP tools but cannot trigger a cycle synchronously.

Rejected: FR-003 requires `run_cycle` to return a `PipelineCycle` summary. A two-process model would require the HTTP gateway to poll a log file or use a shared IPC channel to get the result — adding complexity and a race condition window. The operator would also manage two services.

**Alternative B: Asyncio background task instead of thread**
Replace `threading.Thread` with an asyncio background task created with `asyncio.create_task()` inside the FastMCP server lifespan.

Rejected: `pipeline_orchestrator.runner.run_cycle()` calls `asyncio.run()` internally (to invoke the async `check_new_deals_handler()`). Calling `asyncio.run()` from inside an already-running event loop raises `RuntimeError: This event loop is already running`. A thread avoids event-loop nesting without requiring changes to `runner.run_cycle()`. If `runner.run_cycle()` is ever refactored to be natively async, this decision can be revisited.

**Alternative C: External scheduler (cron, APScheduler, Celery)**
Use a system cron job or a Python scheduling library to trigger cycles independently of the gateway HTTP process.

Rejected: Cron triggers a new process per cycle, making synchronous `run_cycle` results impossible to return over HTTP. APScheduler and Celery add dependencies (Celery requires a broker) that violate Constitution Principle I. The existing sleep-loop model reimplemented in a thread costs zero and requires zero new dependencies.

## References

- Feature Spec: `specs/005-mcp-dashboard/spec.md` (FR-003, FR-005, FR-007)
- Implementation Plan: `specs/005-mcp-dashboard/plan.md` (Decision 3)
- Research: `specs/005-mcp-dashboard/research.md` (Decision 3 — Scheduler Integration Strategy)
- Related ADRs: ADR-0004 (HTTP transport that enables the persistent gateway requiring this scheduler), ADR-0002 (file-based state store accessed by run_cycle())
- Evaluator Evidence: `history/prompts/005-mcp-dashboard/0002-mcp-gateway-dashboard-plan-complete.plan.prompt.md`
