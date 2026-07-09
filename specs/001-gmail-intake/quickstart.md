# Quickstart: Gmail Intake & Deal Detection

**Branch**: `001-gmail-intake` | **Date**: 2026-07-09
**Audience**: Operator setting up `check_new_deals` for the first time

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | `python3 --version` to check |
| pip | ≥23 | Bundled with Python 3.11 |
| Google Cloud project | — | With Gmail API enabled; OAuth consent screen configured (Production) |
| Gemini API key | — | From Google AI Studio (free tier); no credit card needed |
| Gmail account | — | The inbox to poll; must be on the OAuth consent screen's test/allowed list (or a verified production app) |

---

## Step 1 — Install dependencies

From the repo root:

```bash
pip install -e ".[dev]"
```

This installs:
- `fastmcp`, `google-api-python-client`, `google-auth-oauthlib`, `google-generativeai`, `portalocker`
- Dev extras: `pytest`, `pytest-asyncio`

---

## Step 2 — Set up environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
# Required
GMAIL_CREDENTIALS_PATH=/absolute/path/to/credentials.json
GEMINI_API_KEY=your-gemini-api-key-here

# Optional (defaults shown)
STATE_STORE_PATH=./data/processed_ids.json
MAX_MESSAGES_PER_POLL=50
```

**`credentials.json`** is the OAuth client credentials file downloaded from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs → Download JSON. **Never commit this file.**

---

## Step 3 — One-time OAuth authorisation (offline setup)

This step runs once per machine. It opens a browser, you log in, and a `token.json`
file is saved. After this, the server runs headlessly forever.

```bash
python -m gmail_intake.setup_oauth
```

Expected output:
```
Please visit this URL to authorize this application: https://accounts.google.com/o/...
Authorization complete. Token saved to /path/to/token.json
```

`token.json` is saved in the same directory as `credentials.json`. **Never commit `token.json`.**

Verify both files are gitignored:

```bash
git check-ignore -v /path/to/credentials.json
git check-ignore -v /path/to/token.json
```

---

## Step 4 — Verify the state store directory

```bash
mkdir -p data/
# data/processed_ids.json is created automatically on first run
```

---

## Step 5 — Run the MCP server

```bash
python -m gmail_intake.server
```

The server starts and listens on stdio for MCP calls. You will not see output until
OpenClaw connects and invokes `check_new_deals`.

To test it directly without OpenClaw:

```bash
python -c "
import asyncio, json
from gmail_intake.server import check_new_deals_handler
result = asyncio.run(check_new_deals_handler())
print(json.dumps(result, indent=2))
"
```

---

## Step 6 — Configure OpenClaw

Add the following to your OpenClaw MCP server config (location depends on your
OpenClaw version — typically `~/.openclawrc.json` or `openclawrc.json` in the repo):

```json
{
  "mcpServers": {
    "gmail-intake": {
      "command": "python",
      "args": ["-m", "gmail_intake.server"],
      "cwd": "/absolute/path/to/openclaw-deal-scout",
      "env": {
        "GMAIL_CREDENTIALS_PATH": "/absolute/path/to/credentials.json",
        "GEMINI_API_KEY": "your-gemini-api-key",
        "STATE_STORE_PATH": "/absolute/path/to/data/processed_ids.json",
        "MAX_MESSAGES_PER_POLL": "50"
      }
    }
  }
}
```

After saving, restart OpenClaw. It will spawn the Python server as a subprocess and
connect via stdio MCP transport.

---

## Step 7 — Run the test suite

**Unit tests** (no external deps; run any time):

```bash
pytest tests/unit/ -v
```

**Contract tests** (validates tool return shape; no Gmail or Gemini needed):

```bash
pytest tests/contract/ -v
```

**Integration tests** (requires live sandbox Gmail + `GEMINI_API_KEY`):

```bash
# Seed your test Gmail inbox with a mix of deal and non-deal emails first
pytest tests/integration/ -v
```

Expected integration test output:
```
tests/integration/test_check_new_deals.py::test_deal_classification PASSED
tests/integration/test_check_new_deals.py::test_idempotent_rerun PASSED
tests/integration/test_check_new_deals.py::test_empty_inbox PASSED
```

---

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `GMAIL_CREDENTIALS_PATH is not set` | Missing env var | Check `.env` is loaded; use `python-dotenv` or `export` the var |
| `File not found: credentials.json` | Wrong path in `GMAIL_CREDENTIALS_PATH` | Use absolute path |
| `Token has been expired or revoked` | `token.json` was revoked or deleted | Re-run `python -m gmail_intake.setup_oauth` |
| `concurrent invocation` error | Another instance is running against the same state store | Stop the other instance; delete `{STATE_STORE_PATH}.lock` if stale |
| `State store unreadable` | `processed_ids.json` is corrupted or permission-denied | Check file permissions; if corrupted, back it up and delete it (next run starts fresh) |
| Gemini 429 errors | Free-tier quota exhausted (~15 req/min) | Reduce `MAX_MESSAGES_PER_POLL` or space out invocations; the retry logic handles transient 429s automatically |

---

## Gitignore entries (verify these are present)

```gitignore
# Secrets — never commit
credentials.json
credentials.json.json
token.json
.env

# State store
data/processed_ids.json
data/*.lock
data/*.tmp
```
