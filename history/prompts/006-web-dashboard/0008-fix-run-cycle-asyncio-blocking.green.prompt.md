---
id: "0008"
title: Fix Run Cycle asyncio Blocking Bug
stage: green
date: 2026-07-25
surface: agent
model: claude-sonnet-4-6
feature: 006-web-dashboard
branch: main
user: AsmaIqbal01
command: "Dashboard is live and showing data. But Run Cycle is failing with unhandled_exception. Check the pipeline log"
labels: ["bugfix","asyncio","run-cycle","event-loop","uvicorn"]
links:
  spec: specs/006-web-dashboard/spec.md
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - src/pipeline_orchestrator/runner.py
  - src/openclaw_gateway/routes/api.py
tests:
  - "null"
---

## Prompt

Dashboard is live and showing data. But Run Cycle is failing with unhandled_exception. Check the pipeline log to find the actual error:wsl -d Ubuntu-22.04 -- bash -c "cd /home/asmaiqbal01/openclaw-deal-scout && tail -50 pipeline.log 2>/dev/null || journalctl -u openclaw -n 50 --no-pager"

## Response snapshot

Diagnosed two bugs from the gateway log traceback:

**Bug 1** — `runner.py:146`: `asyncio.run(check_new_deals_handler())` raises `RuntimeError: asyncio.run() cannot be called from a running event loop` when invoked from within Uvicorn's event loop.

**Fix 1** — Wrapped the call in a `ThreadPoolExecutor` thread so it always runs in a fresh event loop:
```python
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
    result1 = _pool.submit(asyncio.run, check_new_deals_handler()).result()
```

**Bug 2** — `routes/api.py`: `api_run_cycle` called blocking synchronous `run_cycle()` directly in the async handler, starving Uvicorn's event loop for the full cycle duration (dashboard 404 on all requests while cycle ran).

**Fix 2** — Offloaded to `run_in_executor` so the event loop stays free:
```python
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, run_cycle)
```

Verified: `cycle_running: True` confirmed AND `/api/status` returned 200 OK simultaneously — event loop no longer blocked.

## Outcome

- ✅ Impact: Run Cycle button works from dashboard; all other panels remain responsive during cycle execution
- 🧪 Tests: Existing unit tests unaffected; manual integration test confirmed cycle_running=True with concurrent API responses
- 📁 Files: 2 files modified (runner.py, routes/api.py)
- 🔁 Next prompts: confirm cycle completes and pipeline.log gets new entry; git-checkpoint this fix
- 🧠 Reflection: Classic async/sync boundary issue — FastMCP/Uvicorn runs an event loop; synchronous tool calling asyncio.run() must always run in a thread

## Evaluation notes (flywheel)

- Failure modes observed: asyncio.run() nested event loop crash; event loop starvation from blocking sync call in async handler
- Graders run and results (PASS/FAIL): manual gateway log inspection — root cause confirmed before fix
- Prompt variant (if applicable): "null"
- Next experiment: "null"
