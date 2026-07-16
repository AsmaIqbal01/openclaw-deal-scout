import logging
import time

import requests

from crm_logger.models import (
    HubSpot401Error,
    HubSpotMissingResourceIdError,
    HubSpotRateLimitError,
    HubSpotResponseError,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.hubapi.com"
_INTER_CALL_DELAY = 0.1  # seconds after every non-401 response (SC-006 rate guard)


class HubSpotClient:
    """Low-level HubSpot REST client.

    All network calls go through `_call()`, which applies the 100 ms
    inter-call delay and raises typed exceptions for non-success responses.
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )
        self._call_count: int = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def reset_call_count(self) -> None:
        self._call_count = 0

    def _call(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        msg_id: str | None = None,
        call_type: str | None = None,
    ) -> dict:
        """Execute a single authenticated HubSpot API request.

        - Raises HubSpot401Error  immediately (no sleep) on 401.
        - Sleeps 100 ms after every non-401 response.
        - Raises HubSpotRateLimitError on 429.
        - Raises HubSpotResponseError on any other non-2xx.
        """
        url = f"{_BASE_URL}{path}"
        logger.debug(
            "HubSpot call #%d: %s %s (msg_id=%s, type=%s)",
            self._call_count + 1,
            method,
            path,
            msg_id,
            call_type,
        )

        resp = self._session.request(method, url, json=body)
        self._call_count += 1

        if resp.status_code == 401:
            raise HubSpot401Error(f"401 Unauthorized on {method} {path}")

        time.sleep(_INTER_CALL_DELAY)

        if resp.status_code == 429:
            raise HubSpotRateLimitError(f"429 Too Many Requests on {method} {path}")

        if not resp.ok:
            raise HubSpotResponseError(resp.status_code, resp.text)

        return resp.json()

    # ------------------------------------------------------------------
    # Contact operations (implemented in Phase 3 — T011-T013)
    # ------------------------------------------------------------------

    def search_contact(self, email: str, *, msg_id: str | None = None) -> str | None:
        """Search for a contact by email; return the lowest-ID match or None."""
        body = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "email",
                    "operator": "EQ",
                    "value": email,
                }]
            }],
            "properties": ["email"],
        }
        resp = self._call(
            "POST",
            "/crm/v3/objects/contacts/search",
            body=body,
            msg_id=msg_id,
            call_type="search_contact",
        )
        results = resp.get("results", [])
        if not results:
            return None
        if len(results) > 1:
            logger.warning(
                "HubSpot: %d contacts found for %s — selecting lowest ID", len(results), email
            )
        return str(min(results, key=lambda r: int(r["id"]))["id"])

    def upsert_contact(
        self,
        email: str,
        firstname: str,
        lastname: str,
        *,
        msg_id: str | None = None,
    ) -> str:
        """Return existing contact ID or create a new contact; raise on missing ID."""
        existing_id = self.search_contact(email, msg_id=msg_id)
        if existing_id:
            return existing_id

        body = {
            "properties": {
                "email":     email,
                "firstname": firstname,
                "lastname":  lastname,
            }
        }
        resp = self._call(
            "POST",
            "/crm/v3/objects/contacts",
            body=body,
            msg_id=msg_id,
            call_type="create_contact",
        )
        contact_id = resp.get("id")
        if not contact_id:
            raise HubSpotMissingResourceIdError(
                f"contact create response missing 'id' for email={email}"
            )
        return str(contact_id)

    def create_deal(
        self,
        dealname: str,
        deal_category: str,
        confidence_score: float,
        deal_summary: str,
        received_date_ms: int,
        gmail_message_id: str,
        contact_id: str,
        *,
        msg_id: str | None = None,
    ) -> str:
        """Create a deal with embedded contact association; return HubSpot deal ID."""
        body = {
            "properties": {
                "dealname":                  dealname,
                "openclaw_deal_category":    deal_category,
                "openclaw_confidence_score": str(confidence_score),
                "openclaw_deal_summary":     deal_summary,
                "openclaw_received_date":    str(received_date_ms),
                "openclaw_gmail_message_id": gmail_message_id,
            },
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId":   3,
                        }
                    ],
                }
            ],
        }
        resp = self._call(
            "POST",
            "/crm/v3/objects/deals",
            body=body,
            msg_id=msg_id,
            call_type="create_deal",
        )
        deal_id = resp.get("id")
        if not deal_id:
            raise HubSpotMissingResourceIdError(
                f"deal create response missing 'id' for gmail_message_id={gmail_message_id}"
            )
        return str(deal_id)
