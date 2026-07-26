"""build_send_service — Gmail API client for outbound email (gmail.send scope)."""
from __future__ import annotations

import logging
import os

import google.auth.transport.requests
import google.oauth2.credentials
import googleapiclient.discovery

from email_scheduler.models import AuthError

logger = logging.getLogger(__name__)

SEND_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def build_send_service(credentials_path: str):
    """
    Load OAuth token from token.json (co-located with credentials_path),
    refresh if expired, and return an authenticated Gmail API service client.

    Mirrors gmail_intake.gmail_client.build_service() but uses gmail.send scope.
    Raises AuthError on any credential or refresh failure.
    """
    token_path = os.path.join(
        os.path.dirname(os.path.abspath(credentials_path)), "token.json"
    )

    try:
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            token_path, SEND_SCOPES
        )
    except FileNotFoundError as exc:
        logger.error(
            "Gmail send token not found at %s — run OAuth consent to add gmail.send scope",
            token_path,
        )
        raise AuthError(f"token file not found: {token_path}") from exc
    except Exception as exc:
        logger.error("Gmail send credential load failed: %s", exc)
        raise AuthError(str(exc)) from exc

    if creds.expired:
        if not creds.refresh_token:
            logger.error(
                "Gmail send credentials expired and no refresh token available"
            )
            raise AuthError("credentials expired and no refresh token available")
        try:
            creds.refresh(google.auth.transport.requests.Request())
        except Exception as exc:
            logger.error("Gmail send token refresh failed: %s", exc)
            raise AuthError(str(exc)) from exc

    return googleapiclient.discovery.build("gmail", "v1", credentials=creds)
