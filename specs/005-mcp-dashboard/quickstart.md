# Quickstart: OpenClaw MCP Gateway + Dashboard

**Feature**: `005-mcp-dashboard` | **Date**: 2026-07-23

---

## Prerequisites

- Python 3.12, virtualenv active
- `.env` loaded with all required env vars (see existing `.env` file)
- `pip install -e .` run after new `pyproject.toml` entry points are added

---

## Scenario 1 — Start the gateway and open the dashboard

```bash
# Start gateway (HTTP server on 127.0.0.1:18789 + scheduler loop)
source .env
SCHEDULER_MODE=gateway python -m openclaw_gateway

# In another terminal: open the dashboard
openclaw dashboard
# → opens http://127.0.0.1:18789 in default browser
```

---

## Scenario 2 — Check gateway health from the CLI

```bash
# Quick status
openclaw gateway status
# → RUNNING / STOPPED + uptime + last cycle

# Full health check
openclaw doctor
# → per-component PASS/FAIL for all 5 services
```

---

## Scenario 3 — Trigger a manual pipeline run

```bash
# From CLI (calls run_cycle MCP tool)
openclaw run
# → blocks until cycle completes, prints cycle summary

# Or click "Run Now" in the dashboard at http://127.0.0.1:18789
```

---

## Scenario 4 — Deploy via systemd (production)

```bash
# Copy updated service file (Type=simple, invokes openclaw_gateway)
sudo cp deploy/openclaw.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start persistent gateway (replaces one-shot timer approach)
sudo systemctl enable --now openclaw.service

# Check status
openclaw gateway status
sudo journalctl -u openclaw.service -n 50
```

---

## Scenario 5 — Verify Claude Code independence

```bash
# Run the independence gate test
python -m pytest tests/unit/test_claude_code_independence.py -v
# → PASS: 0 Claude Code references found in src/

# Confirm pipeline works without Claude Code
which claude 2>/dev/null || echo "Claude Code not installed"
openclaw run  # should complete normally
```

---

## Scenario 6 — LAN access from another device

```bash
# In .env, add:
GATEWAY_HOST=0.0.0.0

# Restart gateway
systemctl restart openclaw.service

# From phone or laptop on same network:
# http://<host-machine-ip>:18789
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STATE_STORE_PATH` | Yes | — | Path to `processed_ids.json` |
| `GMAIL_CREDENTIALS_PATH` | Yes | — | OAuth credentials JSON |
| `GEMINI_API_KEY` | Yes | — | Gemini API key |
| `HUBSPOT_PRIVATE_APP_TOKEN` | Yes | — | HubSpot service token |
| `DISCORD_WEBHOOK_URL` | Yes | — | Discord webhook URL |
| `NOTIFIER` | No | `discord` | `discord` or `noop` |
| `GATEWAY_HOST` | No | `127.0.0.1` | Gateway bind address |
| `GATEWAY_PORT` | No | `18789` | Gateway port |
| `SCHEDULER_MODE` | No | `gateway` | `gateway` \| `loop` \| `systemd` |
| `POLL_INTERVAL_MINUTES` | No | `15` | Auto-cycle interval |
| `LOCK_TIMEOUT_MINUTES` | No | `30` | Stale lock timeout |
| `MAX_PENDING_RETRIES` | No | `10` | Max CRM/notify retries |
