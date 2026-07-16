"""CRM Logger — cycle orchestration.

run_crm_cycle() processes one polling cycle:
- US1 (T015): iterate deal_extracted entries, call log_deal() for each
- US4 (T028): drain crm-pending entries before deal_extracted (drain-first)
- US3 (T025): 90-call circuit breaker — defer remaining deals to crm-pending
- US5 (T035-T037): 401 consecutive-cycle suspension gate
"""

import logging

from crm_logger.client import HubSpotClient
from crm_logger.models import CrmCycleResult, HubSpot401Error
from crm_logger.state_store import (
    get_new_deals,
    get_pending_deals,
    read_401_counter,
    read_crm_store,
    write_401_counter,
    write_crm_outcome,
)
from crm_logger.log_deal import log_deal

logger = logging.getLogger(__name__)

_CIRCUIT_BREAKER_LIMIT = 90
_SUSPENSION_THRESHOLD = 3


def run_crm_cycle(
    state_path: str,
    token: str,
    *,
    is_startup: bool = False,
) -> CrmCycleResult:
    """Process one CRM sync cycle.

    Args:
        state_path:  Path to processed_ids.json.
        token:       HubSpot private-app token.
        is_startup:  When True, a suspended cycle resets the counter instead
                     of returning immediately (models a daemon restart).

    Returns:
        CrmCycleResult with status='ok' and counters. suspended=True if the
        cycle was skipped due to consecutive 401 suspension.
    """
    # T037: Suspension gate — check before any HubSpot calls
    counter = read_401_counter(state_path)
    if counter >= _SUSPENSION_THRESHOLD:
        if is_startup:
            logger.warning(
                "crm: restarting after suspension — resetting consecutive_401_cycles to 0"
            )
            write_401_counter(state_path, 0)
        else:
            logger.fatal(
                "crm: suspended — consecutive_401_cycles=%d ≥ %d; no calls made this cycle",
                counter,
                _SUSPENSION_THRESHOLD,
            )
            return CrmCycleResult(status="ok", suspended=True)

    store = read_crm_store(state_path)
    client = HubSpotClient(token)

    crm_logged = 0
    crm_pending = 0
    skipped = 0
    had_401 = False
    had_success = False

    # T028: Drain-first — pending entries processed before new entries
    pending = get_pending_deals(store)
    new = get_new_deals(store)
    all_deals = pending + new

    for idx, deal in enumerate(all_deals):
        # T025: Circuit breaker — defer all remaining deals when limit reached
        if client.call_count >= _CIRCUIT_BREAKER_LIMIT:
            remaining = all_deals[idx:]
            logger.warning(
                "crm: circuit breaker fired at %d calls — deferring %d remaining deal(s)",
                client.call_count,
                len(remaining),
            )
            for deferred in remaining:
                write_crm_outcome(
                    state_path,
                    deferred["gmail_message_id"],
                    "crm-pending",
                    error_reason="circuit_breaker_deferred",
                )
                crm_pending += 1
            break

        try:
            outcome = log_deal(deal, client, state_path)
        except HubSpot401Error:
            # T035: Within-cycle 401 abort — defer all remaining (including current)
            had_401 = True
            remaining = all_deals[idx + 1:]
            for deferred in remaining:
                write_crm_outcome(
                    state_path,
                    deferred["gmail_message_id"],
                    "crm-pending",
                    error_reason="cycle_aborted_401",
                )
                crm_pending += 1
            # Current deal was already handled inside log_deal (it raised before writing)
            # Mark it crm-pending here
            write_crm_outcome(
                state_path,
                deal["gmail_message_id"],
                "crm-pending",
                error_reason="cycle_aborted_401",
            )
            crm_pending += 1
            break

        if outcome == "crm-logged":
            crm_logged += 1
            had_success = True
        elif outcome == "crm-pending":
            crm_pending += 1
        else:
            skipped += 1

    # T036: Cross-cycle 401 counter management
    if had_401 and not had_success:
        # Qualifying 401 cycle — increment counter
        new_count = read_401_counter(state_path) + 1
        write_401_counter(state_path, new_count)
        logger.warning(
            "crm: qualifying 401 cycle — consecutive_401_cycles now %d", new_count
        )
    elif had_success:
        # Any success resets the counter
        write_401_counter(state_path, 0)

    return CrmCycleResult(
        status="ok",
        crm_logged=crm_logged,
        crm_pending=crm_pending,
        skipped=skipped,
    )
