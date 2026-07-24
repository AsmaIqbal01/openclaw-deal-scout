# Quickstart: 006-web-dashboard

**Date**: 2026-07-24 | **Branch**: `006-web-dashboard`

---

## Prerequisites

- Gateway running: `python3.12 -m openclaw_gateway` (or `systemctl start openclaw`)
- Browser: Chrome, Firefox, or Safari (desktop)

---

## Open the Dashboard

```bash
# Option 1 — CLI (recommended)
openclaw dashboard
# → prints "Opening OpenClaw dashboard at http://127.0.0.1:18790 ..."
# → opens browser automatically

# Option 2 — direct URL
open http://127.0.0.1:18790       # macOS
xdg-open http://127.0.0.1:18790  # Linux
# Or paste http://127.0.0.1:18790 into any browser
```

---

## What You'll See

```
┌─────────────────────────────────────────────────┐
│  🦅 OpenClaw Deal Scout           [Run Cycle]   │
├──────────────────┬──────────────────────────────┤
│  STATUS          │  QUOTA                       │
│  ● HEALTHY       │  342 / 1500 requests (22.8%) │
│  Uptime: 2h 14m  │  ████░░░░░░░░░░░░░░░░░░░░░░ │
│  Last run: 10:05 │  12 cycles today             │
├──────────────────┴──────────────────────────────┤
│  COMPONENTS                                      │
│  ✅ gmail   ✅ gemini   ✅ hubspot               │
│  ✅ discord ✅ state    ✅ log                   │
├─────────────────────────────────────────────────┤
│  RECENT CYCLES (last 20)                        │
│  10:05  5 emails  1 CRM  1 notified  ✅         │
│  09:30  2 emails  0 CRM  0 notified  ⚠ quota   │
├─────────────────────────────────────────────────┤
│  DEALS  [Filter: all ▼]  47 total               │
│  partner@example.co.uk — Partnership inquiry    │
│  CRM: logged  Notify: sent  2026-07-23 09:14    │
│  ...                                            │
└─────────────────────────────────────────────────┘
```

---

## Run a Manual Cycle

1. Click **Run Cycle** (top-right).
2. Button shows spinner; page refreshes status every 2s.
3. When cycle completes, a result banner shows email/CRM/notify counts.
4. Button re-enables.

> If pipeline is already running, you'll see "Pipeline busy — try again shortly."

---

## Filter Deals by Status

Use the **Filter** dropdown above the deals list:

| Filter | Shows |
|--------|-------|
| `all` | Every extracted deal |
| `crm_pending` | Deals not yet logged to HubSpot |
| `crm_failed` | Deals that failed HubSpot logging |
| `notify_pending` | Deals not yet sent to Discord |
| `notify_failed` | Deals that failed Discord delivery |
| `complete` | Deals fully processed (CRM logged + notified) |

---

## Auto-Refresh

All panels refresh automatically every **60 seconds**. A small "Last updated" timestamp shows when data was last fetched. No manual refresh needed.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Gateway offline" banner | Gateway process stopped | `systemctl start openclaw` or `python3.12 -m openclaw_gateway` |
| Run Cycle button stuck | Long-running cycle (free-tier Gemini can take a few minutes) | Wait up to 90s; if timeout message appears, check `pipeline.log` |
| Deals panel empty | No emails processed yet, or state store empty | Run a cycle manually to process pending emails |
| Quota warning shown | Gemini free tier hit today | Wait until midnight UTC; quota resets daily |
