# Contract: `NotifierContract` Adapter Interface

**Feature**: `003-discord-notification`
**Date**: 2026-07-17

---

## Overview

`NotifierContract` is a `typing.Protocol` that all notification adapters must
satisfy structurally. Adding a new adapter (e.g., `SlackAdapter`) requires only
implementing the `notify` method — no import of the Protocol class, no
inheritance, no changes to core pipeline files.

---

## Protocol Definition

```python
from typing import Protocol, Literal

class NotifierContract(Protocol):
    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]:
        """
        Attempt to deliver a notification for the given deal.

        Args:
            deal: A dict containing all nine DealPayload fields plus status fields
                  from the state store. The adapter MUST read only the fields it
                  needs and MUST ignore unknown fields.

        Returns:
            "discord-notified"           — delivery confirmed (HTTP 2xx or equivalent)
            "crm-logged-notify-pending"  — delivery failed; caller marks deal retryable

        Contract:
            - MUST NOT raise exceptions; return "crm-logged-notify-pending" on any failure
            - MUST NOT modify the state store or deal dict
            - MUST be idempotent from the caller's perspective (idempotency is
              enforced by notify_deal() before calling this method)
        """
        ...
```

---

## `DiscordAdapter`

```python
class DiscordAdapter:
    def __init__(self, webhook_url: str, timeout: tuple[int, int] = (5, 10)) -> None:
        """
        Args:
            webhook_url: Full Discord webhook URL. Raises EnvironmentError if empty/None.
            timeout: (connect_timeout_s, read_timeout_s). Default (5, 10).
        """
        ...

    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]:
        ...
```

**HTTP call spec**:
- Method: POST
- URL: `webhook_url`
- Headers: `{"Content-Type": "application/json"}`
- Body: `format_embed(deal)` output (see data-model.md)
- Timeout: `(5, 10)` — connect 5 s, read 10 s
- HTTP 2xx → return `"discord-notified"`
- HTTP 429 → log WARN with `retry_after` from response body → return `"crm-logged-notify-pending"`
- HTTP 400 → log WARN (likely embed format error) → return `"crm-logged-notify-pending"`
- HTTP 4xx (other) → log WARN → return `"crm-logged-notify-pending"`
- HTTP 5xx → log WARN → return `"crm-logged-notify-pending"`
- `requests.exceptions.Timeout` → log WARN → return `"crm-logged-notify-pending"`
- Any other exception → log WARN → return `"crm-logged-notify-pending"`
- **Never raises** (all exceptions caught internally)

---

## `NoopAdapter`

```python
class NoopAdapter:
    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]:
        """Always returns "discord-notified". Used for NOTIFIER=noop (testing/dry-run)."""
        return "discord-notified"
```

---

## `get_adapter()` Factory

```python
def get_adapter(notifier: str, env: dict) -> NotifierContract:
    """
    Args:
        notifier: Value of NOTIFIER env var.
        env: Environment dict (typically os.environ).

    Returns:
        Instantiated adapter satisfying NotifierContract.

    Raises:
        EnvironmentError: If notifier is not a known adapter name, or if
                          required env vars for the chosen adapter are missing.

    Known adapters:
        "discord" → DiscordAdapter(webhook_url=env["DISCORD_WEBHOOK_URL"])
        "noop"    → NoopAdapter()
    """
    ...
```

**Fail-fast rules**:
- `NOTIFIER` missing → `EnvironmentError("NOTIFIER env var is required")`
- `NOTIFIER` unknown value → `EnvironmentError(f"Unknown notifier: '{notifier}'. Known: discord, noop")`
- `NOTIFIER=discord` and `DISCORD_WEBHOOK_URL` missing → `EnvironmentError("DISCORD_WEBHOOK_URL not set")`

---

## Adding a New Adapter (Slack Example)

To add `SlackAdapter`:

1. Create `src/discord_notifier/slack_adapter.py` with a class implementing `notify(self, deal) -> Literal[...]`
2. In `adapter.py`, add `"slack"` case to `get_adapter()` dispatch and import `SlackAdapter`
3. Set `NOTIFIER=slack` and `SLACK_WEBHOOK_URL=<url>` in `.env`

**No other files change.** `gmail_intake/`, `crm_logger/`, `orchestrator.py`,
`server.py`, `state_store.py`, `notifier.py`, and `formatter.py` are all
unmodified.

---

## Unit Test Scenarios (adapter.py)

```python
# DiscordAdapter.notify:
# T1: HTTP 200 → "discord-notified"
# T2: HTTP 204 → "discord-notified"
# T3: HTTP 429 with retry_after → "crm-logged-notify-pending" + WARN log
# T4: HTTP 400 (embed error) → "crm-logged-notify-pending" + WARN log
# T5: HTTP 500 → "crm-logged-notify-pending" + WARN log
# T6: requests.Timeout → "crm-logged-notify-pending" + WARN log
# T7: ConnectionError → "crm-logged-notify-pending" + WARN log
# T8: Empty webhook_url → EnvironmentError raised at __init__

# get_adapter:
# T9: NOTIFIER=discord, webhook set → DiscordAdapter returned
# T10: NOTIFIER=noop → NoopAdapter returned
# T11: NOTIFIER missing → EnvironmentError
# T12: NOTIFIER=unknown → EnvironmentError
# T13: NOTIFIER=discord, webhook missing → EnvironmentError
```
