import logging
import os

from discord_notifier.adapter import get_adapter
from discord_notifier.models import (
    NotificationCycleResult,
    NotifyConcurrentError,
    NotifyStateStoreReadError,
)
from discord_notifier.notifier import notify_deal
from discord_notifier.state_store import (
    acquire_lock,
    get_pending_notifications,
    get_ready_to_notify,
    read_notify_store,
)

logger = logging.getLogger(__name__)


def run_notify_cycle(
    state_path: str,
    *,
    notifier_name: str | None = None,
    env: dict | None = None,
) -> NotificationCycleResult:
    """Run one full notification cycle against the state store.

    Drain-first ordering (FR-007): pending entries are processed before
    crm-logged entries so a previous partial failure is retried first.

    Per-deal exceptions are caught and counted as pending — a single bad
    entry never aborts the cycle.

    Returns a NotificationCycleResult summarising the cycle outcome.
    """
    if env is None:
        env = dict(os.environ)
    if notifier_name is None:
        notifier_name = env.get("NOTIFIER")

    try:
        adapter = get_adapter(notifier_name, env)
    except EnvironmentError as exc:
        logger.error("Adapter initialisation failed: %s", exc)
        return NotificationCycleResult(status="error", error_details=str(exc))

    lock = None
    try:
        lock = acquire_lock(state_path)
    except NotifyConcurrentError as exc:
        logger.warning("Concurrent invocation detected — aborting cycle")
        return NotificationCycleResult(status="error", error_details=str(exc))

    try:
        try:
            store = read_notify_store(state_path)
        except NotifyStateStoreReadError as exc:
            logger.error("Cannot read state store: %s", exc)
            return NotificationCycleResult(status="error", error_details=str(exc))

        # Drain-first: pending before ready (FR-007)
        pending_entries = get_pending_notifications(store)
        ready_entries = get_ready_to_notify(store)
        work_queue = pending_entries + ready_entries

        discord_notified = 0
        notify_pending = 0
        # Count already-notified entries as skipped without re-calling the adapter
        skipped = sum(
            1 for m in store.get("messages", [])
            if m.get("status") == "discord-notified"
        )

        for deal in work_queue:
            msg_id = deal.get("gmail_message_id", "?")
            try:
                outcome = notify_deal(deal, adapter, state_path)
            except Exception as exc:
                logger.error("Unexpected error notifying %s: %s", msg_id, exc)
                notify_pending += 1
                continue

            if outcome == "discord-notified":
                discord_notified += 1
            elif outcome == "crm-logged-notify-pending":
                notify_pending += 1
            elif outcome == "skipped":
                skipped += 1

        return NotificationCycleResult(
            status="ok",
            discord_notified=discord_notified,
            notify_pending=notify_pending,
            skipped=skipped,
        )
    finally:
        if lock is not None:
            lock.release()
