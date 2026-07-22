# Quickstart: Pipeline Orchestration Integration Scenarios

**Feature**: 004-pipeline-orchestration | **Date**: 2026-07-22

---

## Scenario 1 — First-time setup (loop mode)

```bash
# Install the orchestrator package (same venv as steps 1-3)
pip install -e .

# Set required env vars in .env
POLL_INTERVAL_MINUTES=15
LOCK_TIMEOUT_MINUTES=30
MAX_PENDING_RETRIES=10
SCHEDULER_MODE=loop
PIPELINE_LOG_PATH=/home/<user>/openclaw-deal-scout/pipeline.log
# (STATE_STORE_PATH already set for steps 1-3)

# Run
python -m pipeline_orchestrator
```

Expected output — cycle summary log line after first cycle:
```json
{"ts": "2026-07-22T14:30:05Z", "emails_processed": 0, "crm_logged": 0, "notified": 0, "pending": 0, "errors": []}
```

---

## Scenario 2 — systemd production deployment

```bash
# Copy unit files
sudo cp deploy/openclaw.service /etc/systemd/system/
sudo cp deploy/openclaw.timer /etc/systemd/system/

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw.timer

# Verify timer is active
systemctl status openclaw.timer

# Watch logs
journalctl -u openclaw.service -f
```

---

## Scenario 3 — Concurrent cycle rejection

```bash
# Manually create a non-stale lock
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$(dirname $STATE_STORE_PATH)/.pipeline.lock"

# Trigger orchestrator — it should detect active lock and skip
python -m pipeline_orchestrator
# Expected log: WARN — concurrent cycle detected, skipping

# Remove lock
rm "$(dirname $STATE_STORE_PATH)/.pipeline.lock"
```

---

## Scenario 4 — Stale lock recovery

```bash
# Create a lock with a timestamp 45 minutes ago (beyond default LOCK_TIMEOUT_MINUTES=30)
echo "2026-07-22T13:45:00Z" > "$(dirname $STATE_STORE_PATH)/.pipeline.lock"

# Run orchestrator — stale lock detected, cleared, cycle proceeds
python -m pipeline_orchestrator
# Expected log: WARN — stale lock detected (created 2026-07-22T13:45:00Z), clearing
```

---

## Scenario 5 — Gemini quota exhaustion mid-cycle (SC-017)

```python
# In tests: inject a deal_extracted entry into state store and confirm steps 2+3 run
# even when step 1 raises RateLimitExhaustedError
```

See `tests/integration/test_full_pipeline.py` for the full mock-based test.

---

## Scenario 6 — SIGTERM graceful shutdown

```bash
# Start orchestrator in loop mode
python -m pipeline_orchestrator &
PID=$!

# Send SIGTERM while a cycle is in progress
kill -TERM $PID

# Verify: lock file is absent, process exited 0, cycle summary was emitted
ls "$(dirname $STATE_STORE_PATH)/.pipeline.lock"  # should not exist
echo $?  # should be non-zero (file not found)
```

---

## Key Environment Variables Quick Reference

| Variable | Default | Purpose |
|---|---|---|
| `STATE_STORE_PATH` | required | Path to `processed_ids.json` |
| `POLL_INTERVAL_MINUTES` | `15` | Seconds between cycles (in minutes) |
| `LOCK_TIMEOUT_MINUTES` | `30` | Stale lock threshold (minutes) |
| `PIPELINE_LOG_PATH` | `<state_dir>/pipeline.log` | Rotating log file location |
| `LOG_MAX_BYTES` | `10485760` | Log rotation size (10 MB) |
| `LOG_BACKUP_COUNT` | `3` | Rotated backup files to keep |
| `MAX_PENDING_RETRIES` | `10` | Max drain attempts before `"failed"` |
| `SCHEDULER_MODE` | `loop` | `"loop"` (dev) or `"systemd"` (prod) |
