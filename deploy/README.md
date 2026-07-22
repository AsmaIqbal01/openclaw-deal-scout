# Deployment: OpenClaw Deal Scout

Two deployment modes are supported. Choose **systemd** for production (recommended) or **loop** for dev/test/WSL2 without systemd.

---

## Prerequisites

```bash
# Install the package (same venv as steps 1-3)
pip install -e .

# Copy your .env file to the repo root and ensure these vars are set:
# STATE_STORE_PATH, HUBSPOT_PRIVATE_APP_TOKEN, DISCORD_WEBHOOK_URL,
# GMAIL_CREDENTIALS_PATH, GEMINI_API_KEY, GOOGLE_OAUTH_TOKEN_PATH
```

---

## Mode 1 — systemd timer (production)

### WSL2 prerequisite

Systemd is disabled in WSL2 by default. Enable it once:

```bash
# /etc/wsl.conf  (create if absent)
[boot]
systemd=true
```

Then restart WSL2: `wsl --shutdown` from Windows, reopen Ubuntu.

Verify: `systemctl status` should show active units (not "Failed to connect to bus").

### Install

The unit files use `%i` (systemd instance specifier) so the same files work for any user without editing.

```bash
# Copy unit files
sudo cp deploy/openclaw@.service /etc/systemd/system/openclaw@.service
sudo cp deploy/openclaw.timer    /etc/systemd/system/openclaw.timer

# Reload and enable for your username (replace 'alice' with your Linux username)
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw.timer

# Start immediately (optional)
sudo systemctl start openclaw@$(whoami).service
```

### Verify

```bash
systemctl status openclaw.timer
systemctl list-timers openclaw.timer
journalctl -u openclaw@alice.service -f
```

### Inspect cycle summaries

```bash
tail -f ~/openclaw-deal-scout/data/pipeline.log | python3 -c "import sys,json; [print(json.dumps(json.loads(l),indent=2)) for l in sys.stdin]"
```

### Stop / disable

```bash
sudo systemctl stop openclaw.timer
sudo systemctl disable openclaw.timer
```

---

## Mode 2 — sleep-loop (dev / WSL2 without systemd)

```bash
# In .env set:
SCHEDULER_MODE=loop
POLL_INTERVAL_MINUTES=15

# Run
python -m pipeline_orchestrator
```

The process runs indefinitely, sleeping between cycles. Send `SIGTERM` or `Ctrl-C` to stop after the current cycle completes cleanly.

---

## Cron fallback (no systemd, no loop daemon)

```bash
# Add to crontab (crontab -e):
*/15 * * * * cd /home/alice/openclaw-deal-scout && \
  SCHEDULER_MODE=systemd .venv/bin/python -m pipeline_orchestrator >> /tmp/openclaw-cron.log 2>&1
```

---

## Monitoring checklist

| Check | Command |
|---|---|
| Last cycle summary | `tail -1 data/pipeline.log \| python3 -m json.tool` |
| Lock file stuck? | `ls -la data/.pipeline.lock` (absent = no cycle running) |
| HubSpot 401 suspension | Look for `"crm_suspended"` in pipeline.log errors |
| Gmail auth failure | Look for `"gmail_oauth_failed"` in pipeline.log errors |
| Pending entries | Look for `"pending": N > 0` in pipeline.log |

---

## Environment variables quick reference

| Variable | Required | Default | Notes |
|---|---|---|---|
| `STATE_STORE_PATH` | Yes | — | Path to `processed_ids.json` |
| `POLL_INTERVAL_MINUTES` | No | `15` | Loop mode only; systemd timer controls interval in systemd mode |
| `LOCK_TIMEOUT_MINUTES` | No | `30` | Stale lock clearance threshold |
| `PIPELINE_LOG_PATH` | No | `<state_store_dir>/pipeline.log` | Rotating cycle summary log |
| `LOG_MAX_BYTES` | No | `10485760` (10 MB) | Log rotation size |
| `LOG_BACKUP_COUNT` | No | `3` | Rotated backup files to keep |
| `MAX_PENDING_RETRIES` | No | `10` | Cycles before a pending entry is promoted to failed |
| `SCHEDULER_MODE` | No | `loop` | `loop` or `systemd` |
