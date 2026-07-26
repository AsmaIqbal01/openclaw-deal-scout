"""
Re-authorize Gmail OAuth to combine gmail.readonly + gmail.send into one token.

Usage (from repo root):
    python3 scripts/reauth_gmail.py

The script will:
  1. Read GMAIL_CREDENTIALS_PATH from .env to locate credentials.json
  2. Print an authorization URL — open it in your browser
  3. Prompt you to paste the authorization code
  4. Write the new token.json (co-located with credentials.json) containing both scopes

Run this once. Afterward the pipeline and email scheduler share the same token.json.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env manually (avoids requiring python-dotenv)
# ---------------------------------------------------------------------------
_ENV_PATH = Path(__file__).parent.parent / ".env"

def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env

_env = _load_env(_ENV_PATH)
for k, v in _env.items():
    os.environ.setdefault(k, v)

# ---------------------------------------------------------------------------
# Locate credentials.json
# ---------------------------------------------------------------------------
CREDS_PATH = os.environ.get("GMAIL_CREDENTIALS_PATH", "")
if not CREDS_PATH:
    print("ERROR: GMAIL_CREDENTIALS_PATH not set in .env", file=sys.stderr)
    sys.exit(1)

CREDS_PATH = Path(CREDS_PATH)
if not CREDS_PATH.exists():
    print(f"ERROR: credentials.json not found at {CREDS_PATH}", file=sys.stderr)
    sys.exit(1)

TOKEN_PATH = CREDS_PATH.parent / "token.json"

# ---------------------------------------------------------------------------
# Combined scopes (both packages need these)
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# ---------------------------------------------------------------------------
# OAuth flow — console mode works in WSL without a local browser
# ---------------------------------------------------------------------------
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print(
        "ERROR: google-auth-oauthlib not installed.\n"
        "Run: pip install google-auth-oauthlib",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"\nCredentials : {CREDS_PATH}")
print(f"Token target: {TOKEN_PATH}")
print(f"Scopes      : {SCOPES}\n")

if TOKEN_PATH.exists():
    print(f"Existing token.json found — it will be REPLACED after you authorize.\n")

flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)

# run_console() prints the URL and reads the code from stdin — no browser needed locally
creds = flow.run_console()

# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------
token_data = {
    "token": creds.token,
    "refresh_token": creds.refresh_token,
    "token_uri": creds.token_uri,
    "client_id": creds.client_id,
    "client_secret": creds.client_secret,
    "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    "universe_domain": getattr(creds, "universe_domain", "googleapis.com"),
}

TOKEN_PATH.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
print(f"\n✅ token.json written to: {TOKEN_PATH}")
print(f"   Scopes: {token_data['scopes']}")
print(
    "\nThe pipeline (gmail.readonly) and email scheduler (gmail.send) "
    "now share this token."
)
