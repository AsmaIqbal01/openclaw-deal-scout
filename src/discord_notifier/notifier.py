import logging
from datetime import datetime, timezone
from typing import Literal

from discord_notifier.adapter import NotifierContract
from discord_notifier.state_store import write_notify_outcome

logger = logging.getLogger(__name__)

NotifyOutcome = Literal["discord-notified", "crm-logged-notify-pending", "skipped"]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def notify_deal(deal: dict, adapter: NotifierContract, state_path: str) -> NotifyOutcome:
    """Attempt to deliver a Discord notification for one deal entry.

    Idempotency guard: if status is already 'discord-notified', returns 'skipped'
    immediately with no API call and no state write.

    FR-016: if the Discord delivery succeeds (HTTP 2xx) but the subsequent
    state-store write fails (OSError), logs [ERROR] and returns 'discord-notified'
    so callers know delivery happened. The entry remains in its pre-write status in
    the store, which means it will be retried next cycle — at-least-once delivery.
    """
    msg_id = deal.get("gmail_message_id", "?")
    current_status = deal.get("status")

    if current_status == "discord-notified":
        logger.debug("notify_deal: already notified — skipping %s", msg_id)
        return "skipped"

    outcome = adapter.notify(deal)

    if outcome == "discord-notified":
        try:
            write_notify_outcome(
                state_path,
                msg_id,
                "discord-notified",
                notified_at=_utcnow_iso(),
            )
        except OSError as exc:
            # FR-016: delivery confirmed but state write failed
            logger.error(
                "State write failed after successful Discord delivery for %s: %s",
                msg_id, exc,
            )
        except KeyError as exc:
            logger.error("State write failed — message ID not found: %s", exc)
    else:
        # outcome == "crm-logged-notify-pending"
        raw_reason = getattr(adapter, "_last_error_reason", "") or f"Discord delivery failed for {msg_id}"
        error_reason = raw_reason[:255]
        try:
            write_notify_outcome(
                state_path,
                msg_id,
                "crm-logged-notify-pending",
                notify_error_reason=error_reason,
            )
        except (OSError, KeyError) as exc:
            logger.error("Failed to write pending state for %s: %s", msg_id, exc)

    return outcome
