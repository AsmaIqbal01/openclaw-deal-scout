import logging
import os
from datetime import datetime, timedelta, timezone

import google.auth.transport.requests
import google.oauth2.credentials
import googleapiclient.discovery
from googleapiclient.errors import HttpError

from gmail_intake.models import AuthError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def build_service(credentials_path: str):
    """
    Load OAuth token from token.json (co-located with credentials_path),
    refresh if expired (one attempt), and return an authenticated Gmail service.

    Raises AuthError on any credential or refresh failure.
    """
    token_path = os.path.join(
        os.path.dirname(os.path.abspath(credentials_path)), "token.json"
    )

    try:
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            token_path, SCOPES
        )
    except FileNotFoundError as exc:
        logger.error("Gmail token refresh failed: token file not found at %s", token_path)
        raise AuthError(f"token file not found: {token_path}") from exc
    except Exception as exc:
        logger.error("Gmail token refresh failed: %s", exc)
        raise AuthError(str(exc)) from exc

    if creds.expired:
        if not creds.refresh_token:
            logger.error(
                "Gmail token refresh failed: credentials expired and no refresh token"
            )
            raise AuthError("credentials expired and no refresh token available")
        try:
            creds.refresh(google.auth.transport.requests.Request())
        except Exception as exc:
            logger.error("Gmail token refresh failed: %s", exc)
            raise AuthError(str(exc)) from exc

    return googleapiclient.discovery.build("gmail", "v1", credentials=creds)


def poll_inbox(service, since_ts: str | None, max_messages: int) -> list[dict]:
    """
    Fetch unread messages from the Gmail inbox since since_ts.

    Sorting and capping (FR-003a):
      - All matching messages are fetched and sorted by internalDate ascending.
      - max_messages cap is applied to this full sorted set BEFORE any
        already-processed filter; the caller applies the filter.

    On HttpError or ConnectionError: logs WARN and re-raises for cycle-level abort.
    """
    if since_ts is None:
        after_epoch = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
    else:
        after_epoch = int(datetime.fromisoformat(since_ts.replace("Z", "+00:00")).timestamp())

    query = f"after:{after_epoch} is:unread"

    try:
        # Paginate to collect all matching message ID stubs
        message_stubs: list[dict] = []
        response = service.users().messages().list(userId="me", q=query).execute()
        message_stubs.extend(response.get("messages", []))
        while "nextPageToken" in response:
            response = service.users().messages().list(
                userId="me", q=query, pageToken=response["nextPageToken"]
            ).execute()
            message_stubs.extend(response.get("messages", []))

        # Fetch full message payloads
        messages: list[dict] = []
        for stub in message_stubs:
            msg = service.users().messages().get(
                userId="me", id=stub["id"], format="full"
            ).execute()
            messages.append(msg)

        # Sort oldest-first, then apply max_messages cap (FR-003a)
        messages.sort(key=lambda m: int(m.get("internalDate", 0)))
        return messages[:max_messages]

    except HttpError as exc:
        if exc.resp.status == 429:
            logger.warning("Gmail rate limited mid-poll: %s", exc)
        else:
            logger.error("network failure mid-poll: %s", exc)
        raise
    except ConnectionError as exc:
        logger.error("network failure mid-poll: %s", exc)
        raise
