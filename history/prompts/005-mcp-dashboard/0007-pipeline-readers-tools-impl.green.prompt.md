---
id: "0007"
title: Pipeline Readers and Tools Implementation
stage: green
date: 2026-07-24
surface: agent
model: claude-sonnet-4-6
feature: 005-mcp-dashboard
branch: 005-mcp-dashboard
user: AsmaIqbal01
command: implement T018 through T023
labels: ["green","mcp","readers","pipeline","quota","deals","cycles"]
links:
  spec: specs/005-mcp-dashboard/spec.md
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - tests/unit/test_gateway_readers.py   # created: 17 tests for readers module
  - tests/unit/test_gateway_tools_pipeline.py  # created: 13 tests for pipeline tool functions
  - src/openclaw_gateway/readers.py      # created: read_pipeline_log, read_deals, compute_quota_usage
  - src/openclaw_gateway/tools/pipeline.py  # extended: T021 get_pipeline_cycles, T022 get_deals, T023 get_quota_usage
tests:
  - tests/unit/test_gateway_readers.py (17 tests)
  - tests/unit/test_gateway_tools_pipeline.py (13 tests)
---

## Prompt

implement T018 through T023

## Response snapshot

Implemented 4 files covering Phase 6 (US3 — dashboard pipeline status & deal history):

- **T018**: Created `tests/unit/test_gateway_readers.py` (17 tests). Uses `tmp_path` fixtures with real JSONL log files and JSON state files. Covers: `read_pipeline_log` last-N slice, missing-file → empty list, deque trimming; `read_deals` outcome filter, crm_pending status filter, limit, missing file; `compute_quota_usage` all-keys, cycles_today count, estimated_requests sum, window_date, pct_used formula, missing log → zeros.

- **T019**: Created `tests/unit/test_gateway_tools_pipeline.py` (13 tests). Patches `openclaw_gateway.readers.*` functions and `openclaw_gateway.server._config` via monkeypatch. Covers: `get_pipeline_cycles` keys/limit/total_in_log/empty; `get_deals` keys/filtered_by/total_deals-unfiltered/default-status-all; `get_quota_usage` return passthrough and config forwarding.

- **T020**: Created `src/openclaw_gateway/readers.py` (stdlib only). `_iter_log()` generator handles missing file + bad JSON lines. `read_pipeline_log(n, config)` uses `collections.deque(maxlen=n)`. `read_deals(limit, status_filter, config)` filters `outcome=="deal_extracted"` then applies `_STATUS_FILTERS` dict (crm_pending/crm_failed/notify_pending/notify_failed/complete), returns newest-first. `compute_quota_usage(config)` counts today's UTC cycles, sums emails_processed, computes all 7 QuotaUsage fields.

- **T021–T023**: Rewrote `src/openclaw_gateway/tools/pipeline.py` stubs into real implementations. Each function lazy-imports `openclaw_gateway.server` (for `_config`) and `openclaw_gateway.readers`. `get_pipeline_cycles` makes two reader calls (limited + 99999 for total). `get_deals` makes two calls (filtered-limited + all-unlimited for total_deals). `get_quota_usage` delegates directly to `readers.compute_quota_usage`.

All 269 unit tests pass; independence gate (T008) still green.

## Outcome

- ✅ Impact: All 5 read-only MCP tools now functional; dashboard data endpoints complete (cycles, deals, quota)
- 🧪 Tests: 269/269 pass (30 new for T018+T019; existing 239 unaffected)
- 📁 Files: 4 files created/extended (2 test files, 1 new readers.py, 1 extended pipeline.py)
- 🔁 Next prompts: implement T024–T029 (US4: run_cycle + scheduler + __main__.py)
- 🧠 Reflection: `_STATUS_FILTERS` dict avoids if/elif chains and makes adding new filters trivial; `_iter_log()` generator avoids duplicating try/except in both read_pipeline_log and compute_quota_usage

## Evaluation notes (flywheel)

- Failure modes observed: tasks.md T018 said "status_filter=crm_logged" but contracts say "crm_pending"; contracts are authoritative — used "crm_pending" in tests
- Graders run and results (PASS/FAIL): self-review PASS; 269/269 pytest PASS
- Prompt variant (if applicable): none
- Next experiment: T024–T029 as one chunk (scheduler + run_cycle + __main__.py)
