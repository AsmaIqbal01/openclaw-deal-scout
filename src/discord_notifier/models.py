from dataclasses import dataclass, field
from typing import Literal


class DiscordWebhookError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"Discord HTTP {status_code}: {body[:200]}")
        self.status_code = status_code


class DiscordRateLimitError(DiscordWebhookError):
    def __init__(self, status_code: int, body: str, retry_after: float = 0.0) -> None:
        super().__init__(status_code, body)
        self.retry_after = retry_after


class DiscordTimeoutError(Exception):
    pass


class NotifyStateStoreReadError(Exception):
    pass


class NotifyConcurrentError(Exception):
    pass


NotifyOutcome = Literal["discord-notified", "crm-logged-notify-pending", "skipped"]


@dataclass
class NotificationCycleResult:
    status: str
    discord_notified: int = 0
    notify_pending: int = 0
    skipped: int = 0
    error_details: str | None = None
