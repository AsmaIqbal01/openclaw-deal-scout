import logging
import os

import google.auth.transport.requests
import google.oauth2.credentials
import googleapiclient.discovery

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
