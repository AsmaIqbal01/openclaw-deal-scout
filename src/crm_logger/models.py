from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class HubSpot401Error(Exception):
    """HubSpot returned 401 Unauthorized — credential invalid."""


class HubSpotRateLimitError(Exception):
    """HubSpot returned 429 Too Many Requests."""


class HubSpotResponseError(Exception):
    """HubSpot returned a non-success, non-401, non-429 status code."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"HubSpot {status_code}: {body[:200]}")
        self.status_code = status_code


class HubSpotMissingResourceIdError(Exception):
    """HubSpot returned 200 but response body is missing the expected resource ID."""


class CrmStateStoreReadError(Exception):
    """CRM state store file cannot be read or parsed as valid JSON."""


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

CrmOutcome = Literal["crm-logged", "crm-pending", "skipped"]


@dataclass
class HubSpotContact:
    """A HubSpot contact record as written/read by the CRM Logger."""
    hubspot_id: str
    email:      str
    firstname:  str
    lastname:   str


@dataclass
class HubSpotDeal:
    """A HubSpot deal record as written by the CRM Logger."""
    hubspot_id:                str
    dealname:                  str
    openclaw_deal_category:    str
    openclaw_confidence_score: float
    openclaw_deal_summary:     str
    openclaw_received_date:    int    # Unix epoch milliseconds
    openclaw_gmail_message_id: str


@dataclass
class HubSpotWriteResult:
    """Outcome of a single log_deal() call."""
    outcome:         CrmOutcome
    hubspot_deal_id: str | None = None   # set when outcome == "crm-logged"
    error_reason:    str | None = None   # set when outcome == "crm-pending"


@dataclass
class CrmStateStore:
    """Extended top-level structure of processed_ids.json read by crm_logger."""
    last_poll_time:         str | None
    consecutive_401_cycles: int
    messages:               list[dict] = field(default_factory=list)


@dataclass
class CrmCycleResult:
    """Return value of run_crm_cycle(), forwarded as sync_deals_to_crm tool response."""
    status:        str           # "ok" | "error"
    crm_logged:    int = 0
    crm_pending:   int = 0
    skipped:       int = 0
    suspended:     bool = False
    error_details: str | None = None
