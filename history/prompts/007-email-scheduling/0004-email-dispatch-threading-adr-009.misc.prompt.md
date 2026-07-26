---
id: "0004"
title: Email Dispatch Threading ADR 009
stage: misc
date: 2026-07-26
surface: agent
model: claude-sonnet-4-6
feature: 007-email-scheduling
branch: 007-email-scheduling
user: AsmaIqbal01
command: /sp.adr email-dispatch-threading-model
labels: ["adr","threading","asyncio","email-dispatch","queue-store","concurrency","007-email-scheduling"]
links:
  spec: specs/007-email-scheduling/spec.md
  ticket: "null"
  adr: history/adr/0009-email-dispatch-threading-model-in-process-synchronous-dispatch.md
  pr: "null"
files:
  - history/adr/0009-email-dispatch-threading-model-in-process-synchronous-dispatch.md
tests:
  - "null"
---

## Prompt

/sp.adr email-dispatch-threading-model

## Response snapshot

Checked existing ADRs 0001–0008. ADR-0005 (gateway single-process thread model) is adjacent
but distinct — it covers the HTTP server + pipeline scheduler thread; ADR-0009 covers how the
NEW email scheduler fits within that existing model. No conflict.

Significance test PASS (all 3 criteria): cross-cutting impact on EmailQueueStore, HTTP handlers,
scheduler step 4, and AuditLogger; three alternatives with distinct tradeoffs; will be
questioned if dispatch latency or email volume grows.

Created ADR-0009: Email Dispatch Threading Model — In-Process Synchronous Dispatch.

Decision cluster: dispatch runs inline in step 4 of run_cycle() (no new thread);
threading.Lock for all queue writes; asyncio.to_thread() in HTTP handlers to avoid
event-loop blocking; Python logging.FileHandler for thread-safe audit writes.

Three alternatives documented:
- Alternative A (dedicated background thread): rejected — adds third concurrent context,
  lock coordination complexity, not justified by single-operator volume
- Alternative B (asyncio.Lock + run_coroutine_threadsafe): rejected — couples EmailQueueStore
  to asyncio runtime, complex test setup
- Alternative C (per-request file reads, no lock): rejected — TOCTOU race condition between
  read and write; constant I/O overhead for negligible queue change rate

## Outcome

- ✅ Impact: ADR-0009 created; threading model for email dispatch permanently documented with process diagram and full alternatives
- 🧪 Tests: none (ADR stage)
- 📁 Files: 1 ADR created
- 🔁 Next prompts: /sp.tasks
- 🧠 Reflection: ADR-0009 correctly extends ADR-0005 rather than superseding it — the threading model for the email scheduler is an additive constraint on the existing model, not a replacement

## Evaluation notes (flywheel)

- Failure modes observed: none — create-adr.sh syntax now known from previous run
- Graders run and results (PASS/FAIL): significance test PASS (all 3 criteria met)
- Prompt variant (if applicable): "null"
- Next experiment: "null"
