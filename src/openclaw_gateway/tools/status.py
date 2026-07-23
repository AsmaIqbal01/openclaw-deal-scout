"""Health and status tools for the OpenClaw gateway."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from openclaw_gateway import __version__
from openclaw_gateway.config import GatewayConfig


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_gmail_oauth(credentials_path: Optional[str]) -> dict:
    name = "gmail_oauth"
    if not credentials_path:
        return {
            "name": name, "status": "FAIL", "latency_ms": None,
            "message": "GMAIL_CREDENTIALS_PATH not set",
        }
    token_path = Path(credentials_path).parent / "token.json"
    t0 = time.monotonic()
    try:
        import google.auth.transport.requests
        import google.oauth2.credentials

        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            str(token_path), ["https://www.googleapis.com/auth/gmail.readonly"]
        )
        if creds.expired:
            if not creds.refresh_token:
                return {
                    "name": name, "status": "FAIL", "latency_ms": None,
                    "message": "Token expired and no refresh token. Re-run setup_oauth.py.",
                }
            creds.refresh(google.auth.transport.requests.Request())
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"name": name, "status": "PASS", "latency_ms": latency_ms, "message": None}
    except FileNotFoundError:
        return {
            "name": name, "status": "FAIL", "latency_ms": None,
            "message": f"token.json not found at {token_path}. Re-run setup_oauth.py.",
        }
    except Exception as exc:
        return {"name": name, "status": "FAIL", "latency_ms": None, "message": str(exc)}


def _check_gemini_api(api_key: Optional[str]) -> dict:
    name = "gemini_api"
    if not api_key:
        return {
            "name": name, "status": "FAIL", "latency_ms": None,
            "message": "GEMINI_API_KEY not set",
        }
    t0 = time.monotonic()
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        # Lightweight read-only call — list first model to validate key
        next(iter(client.models.list()), None)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"name": name, "status": "PASS", "latency_ms": latency_ms, "message": None}
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"name": name, "status": "FAIL", "latency_ms": latency_ms, "message": str(exc)}


def _check_hubspot_token(token: Optional[str]) -> dict:
    name = "hubspot_token"
    if not token:
        return {
            "name": name, "status": "FAIL", "latency_ms": None,
            "message": "HUBSPOT_PRIVATE_APP_TOKEN not set",
        }
    t0 = time.monotonic()
    try:
        resp = requests.get(
            "https://api.hubapi.com/crm/v3/properties/deals",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code == 200:
            return {"name": name, "status": "PASS", "latency_ms": latency_ms, "message": None}
        if resp.status_code == 401:
            return {
                "name": name, "status": "FAIL", "latency_ms": latency_ms,
                "message": "Token invalid or expired (HTTP 401)",
            }
        return {
            "name": name, "status": "FAIL", "latency_ms": latency_ms,
            "message": f"Unexpected HTTP {resp.status_code}",
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"name": name, "status": "FAIL", "latency_ms": latency_ms, "message": str(exc)}


def _check_discord_webhook(webhook_url: Optional[str]) -> dict:
    name = "discord_webhook"
    if not webhook_url:
        return {
            "name": name, "status": "FAIL", "latency_ms": None,
            "message": "DISCORD_WEBHOOK_URL not set",
        }
    t0 = time.monotonic()
    try:
        resp = requests.get(webhook_url, timeout=10)
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code in (200, 204):
            return {"name": name, "status": "PASS", "latency_ms": latency_ms, "message": None}
        return {
            "name": name, "status": "FAIL", "latency_ms": latency_ms,
            "message": f"HTTP {resp.status_code}",
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"name": name, "status": "FAIL", "latency_ms": latency_ms, "message": str(exc)}


def _check_state_store(state_store_path: Path) -> dict:
    name = "state_store"
    try:
        if not state_store_path.is_file():
            return {
                "name": name, "status": "FAIL", "latency_ms": None,
                "message": f"File not found: {state_store_path}",
            }
        with open(state_store_path, encoding="utf-8") as fh:
            json.load(fh)
        return {"name": name, "status": "PASS", "latency_ms": None, "message": None}
    except json.JSONDecodeError as exc:
        return {
            "name": name, "status": "FAIL", "latency_ms": None,
            "message": f"Invalid JSON: {exc}",
        }
    except OSError as exc:
        return {"name": name, "status": "FAIL", "latency_ms": None, "message": str(exc)}


def get_gateway_status(config: GatewayConfig) -> dict:
    """Return live gateway runtime state (GatewayStatus schema)."""
    import openclaw_gateway.server as srv

    start = srv._gateway_start_time
    uptime = int(time.time() - start) if start > 0 else None
    return {
        "running": True,
        "uptime_seconds": uptime,
        "version": __version__,
        "host": config.gateway_host if config else "unknown",
        "port": config.gateway_port if config else 0,
        "last_cycle_at": srv._last_cycle_at or "never",
        "cycle_running": srv._cycle_running,
    }


def get_health(config: GatewayConfig) -> dict:
    """Run full health check against all 5 external pipeline components."""
    t_start = time.monotonic()

    components = [
        _check_gmail_oauth(os.environ.get("GMAIL_CREDENTIALS_PATH")),
        _check_gemini_api(os.environ.get("GEMINI_API_KEY")),
        _check_hubspot_token(os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")),
        _check_discord_webhook(os.environ.get("DISCORD_WEBHOOK_URL")),
        _check_state_store(config.state_store_path),
    ]

    overall = "HEALTHY" if all(c["status"] == "PASS" for c in components) else "DEGRADED"
    duration_ms = int((time.monotonic() - t_start) * 1000)

    return {
        "overall": overall,
        "checked_at": _utcnow_iso(),
        "duration_ms": duration_ms,
        "components": components,
    }
