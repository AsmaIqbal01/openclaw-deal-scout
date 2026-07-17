import logging
from typing import Literal, Protocol

import requests

from discord_notifier.formatter import format_embed

logger = logging.getLogger(__name__)


class NotifierContract(Protocol):
    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]:
        """Attempt to deliver a notification. MUST NOT raise; return pending on any failure."""
        ...


class DiscordAdapter:
    def __init__(self, webhook_url: str, timeout: tuple[int, int] = (5, 10)) -> None:
        if not webhook_url:
            raise EnvironmentError("DISCORD_WEBHOOK_URL is empty or not set")
        self._webhook_url = webhook_url
        self._timeout = timeout
        self._last_error_reason: str = ""

    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]:
        embed = format_embed(deal)
        msg_id = deal.get("gmail_message_id", "?")
        self._last_error_reason = ""
        try:
            resp = requests.post(
                self._webhook_url,
                json=embed,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout:
            self._last_error_reason = "Timeout"
            logger.warning(
                "Discord notify timeout for %s (connect=%ss read=%ss)",
                msg_id, self._timeout[0], self._timeout[1],
            )
            return "crm-logged-notify-pending"
        except requests.exceptions.RequestException as exc:
            self._last_error_reason = type(exc).__name__
            logger.warning("Discord notify connection error for %s: %s", msg_id, exc)
            return "crm-logged-notify-pending"

        if resp.status_code == 429:
            retry_after = 0.0
            try:
                retry_after = float(resp.json().get("retry_after", 0.0))
            except Exception:
                pass
            self._last_error_reason = f"HTTP 429 (retry_after={retry_after:.1f}s)"
            logger.warning(
                "Discord rate limited for %s (retry_after=%.1fs)", msg_id, retry_after
            )
            return "crm-logged-notify-pending"

        if not resp.ok:
            self._last_error_reason = f"HTTP {resp.status_code}"
            logger.warning(
                "Discord notify HTTP %s for %s: %s",
                resp.status_code, msg_id, resp.text[:200],
            )
            return "crm-logged-notify-pending"

        logger.info("Discord notified: %s", msg_id)
        return "discord-notified"


class NoopAdapter:
    def notify(self, deal: dict) -> Literal["discord-notified", "crm-logged-notify-pending"]:
        logger.debug("NoopAdapter: skipping Discord delivery for %s", deal.get("gmail_message_id"))
        return "discord-notified"


def get_adapter(notifier: str | None, env: dict) -> NotifierContract:
    """Factory: resolve NOTIFIER name to an instantiated adapter.

    Raises:
        EnvironmentError: if notifier is missing, unrecognised, or required env
                          vars for the chosen adapter are absent.
    """
    if not notifier:
        raise EnvironmentError("NOTIFIER env var is required but not set")

    if notifier == "discord":
        webhook_url = env.get("DISCORD_WEBHOOK_URL", "")
        if not webhook_url:
            raise EnvironmentError("DISCORD_WEBHOOK_URL is required when NOTIFIER=discord")
        return DiscordAdapter(webhook_url=webhook_url)

    if notifier == "noop":
        return NoopAdapter()

    raise EnvironmentError(
        f"Unknown notifier: '{notifier}'. Known adapters: discord, noop"
    )
