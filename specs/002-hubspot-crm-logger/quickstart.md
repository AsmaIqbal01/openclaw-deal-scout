# Quickstart: HubSpot CRM Logger

**Branch**: `002-hubspot-crm-logger` | **Date**: 2026-07-16
**Prereq**: Feature `001-gmail-intake` installed and running (state store at `STATE_STORE_PATH`)

---

## Step 1 — Create a HubSpot Free account

1. Go to [hubspot.com](https://hubspot.com) → "Get started free"
2. Create a free account (no credit card required)
3. Complete onboarding (skip all paid upsells)

---

## Step 2 — Create a Private App token

1. In HubSpot: **Settings → Integrations → Private Apps → Create a private app**
2. Name: `OpenClaw Deal Scout`
3. Under **Scopes**, add:
   - `crm.objects.contacts.read`
   - `crm.objects.contacts.write`
   - `crm.objects.deals.read`
   - `crm.objects.deals.write`
   - `crm.schemas.contacts.read`
   - `crm.schemas.deals.read`
   - `associations.read`
   - `associations.write`
4. Click **Create app** → copy the token (starts with `pat-`)
5. Add to `.env`:
   ```
   HUBSPOT_PRIVATE_APP_TOKEN=pat-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

---

## Step 3 — Create the 5 custom deal properties in HubSpot

1. In HubSpot: **Settings → Properties → Deals → Create property**
2. Create each property exactly as listed:

| Internal name | Label | Type |
|---|---|---|
| `openclaw_deal_category` | OpenClaw Deal Category | Single-line text |
| `openclaw_confidence_score` | OpenClaw Confidence Score | Number (decimal) |
| `openclaw_deal_summary` | OpenClaw Deal Summary | Multi-line text |
| `openclaw_received_date` | OpenClaw Received Date | Date |
| `openclaw_gmail_message_id` | OpenClaw Gmail Message ID | Single-line text |

**Important**: The internal name must match exactly (lowercase, underscores). HubSpot may suggest a different internal name — override it to match the list above. These are the property keys sent in the API `properties` object.

---

## Step 4 — Install the new dependency

```bash
pip install requests
```

All other dependencies (`fastmcp`, `portalocker`, `python-dotenv`) are already installed from feature 001.

---

## Step 5 — Register the MCP tool with OpenClaw

Add the following entry to your OpenClaw MCP server config (e.g., `~/.openclawrc.json` or the equivalent config file for your OpenClaw installation):

```json
{
  "mcpServers": {
    "crm-logger": {
      "command": "python",
      "args": ["-m", "crm_logger.server"],
      "cwd": "/home/asmaiqbal01/openclaw-deal-scout",
      "env": {
        "HUBSPOT_PRIVATE_APP_TOKEN": "${HUBSPOT_PRIVATE_APP_TOKEN}",
        "STATE_STORE_PATH": "${STATE_STORE_PATH}"
      }
    }
  }
}
```

The `gmail-intake` server entry from feature 001 remains unchanged. Both servers run in parallel as child processes of OpenClaw.

---

## Step 6 — Verify the setup (smoke test)

Run the MCP tool directly to confirm the module loads and reads the state store:

```bash
cd /home/asmaiqbal01/openclaw-deal-scout
python -c "
from crm_logger.orchestrator import run_crm_cycle
import os
result = run_crm_cycle(
    state_path=os.environ['STATE_STORE_PATH'],
    token=os.environ['HUBSPOT_PRIVATE_APP_TOKEN'],
)
print(result)
"
```

Expected output with an empty or all-processed state store:
```
CrmCycleResult(status='ok', crm_logged=0, crm_pending=0, skipped=0, suspended=False, error_details=None)
```

---

## Step 7 — First real run

Once feature 001 (`check_new_deals`) has processed at least one confirmed deal (outcome `deal_extracted` in the state store), call `sync_deals_to_crm` via OpenClaw. The deal should appear in HubSpot under **CRM → Deals** within a few seconds.

To verify:
1. Open HubSpot → **CRM → Deals**
2. Find the deal by name (first 252 chars of the email subject)
3. Confirm the custom properties are populated: deal category, confidence score, Gmail message ID
4. Confirm the deal is linked to a contact matching the sender's email

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `HubSpot401Error` on first run | Token pasted incorrectly or missing scopes | Re-check `HUBSPOT_PRIVATE_APP_TOKEN` in `.env`; verify all 8 scopes in HubSpot Private App settings |
| `HubSpotResponseError: 400` on deal create | Custom property not created in HubSpot | Complete Step 3 — all 5 `openclaw_*` properties must exist before first run |
| `CrmStateStoreReadError` | State store path wrong or file corrupted | Check `STATE_STORE_PATH` env var; verify the file path is a native Windows path (not WSL UNC path) on Windows/WSL deployments |
| All deals show `crm_pending: N` and 0 `crm_logged` | HubSpot writes failing silently | Check logs for WARN entries; look for `HubSpotResponseError` reason |
| `suspended: true` in every cycle | 3+ consecutive 401 cycles triggered | Rotate the private-app token in HubSpot → update `HUBSPOT_PRIVATE_APP_TOKEN` → restart agent (restart resets the counter) |
| State store not updated with 9 DealPayload fields | Running old 001 code before 002's `server.py` change | Ensure `gmail_intake/server.py` has been updated to pass `extra_fields` to `append_message` (FR-015 dependency) |
