import base64
import re
from datetime import datetime, timezone
from email.utils import parseaddr

from gmail_intake.models import (
    ClassificationResponse,
    DealPayload,
    InvalidMetadataError,
    SchemaValidationError,
)

_DEAL_CATEGORIES = {"lead", "partnership_inquiry", "vendor_offer", "rfq", "other"}

# --- FR-011 sentence boundary rules (research.md Decision 8) -----------------

_TITLE_ABBREVS = r"(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|Ltd|vs|etc|eg|ie|approx|dept|Fig|No)"
_NON_SENTENCE_DOT = re.compile(
    r"(?:" + _TITLE_ABBREVS + r")\."  # Title abbreviations
    r"|(?:[A-Z]\.){2,}"  # Acronyms: U.K., U.S.A.
    r"|\b[A-Z]\."  # Single initials: J. Smith
)

_SENTENCE_END = re.compile(r"(?<![.!?])[.!?](?=\s|$)")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, excluding title abbreviations, acronyms, initials."""
    protected = _NON_SENTENCE_DOT.sub(lambda m: m.group().replace(".", "\x00"), text)
    # Insert a split marker AFTER each sentence-ending punctuation so the
    # punctuation is preserved in the resulting sentence strings.
    marked = _SENTENCE_END.sub(lambda m: m.group() + "\x01", protected)
    return [p.replace("\x00", ".").strip() for p in marked.split("\x01") if p.strip()]


def truncate_summary(text: str, max_sentences: int = 2, max_chars: int = 500) -> str:
    """FR-011: sentence rule first, then 500-char hard cap at a word boundary."""
    sentences = split_sentences(text)
    truncated = " ".join(sentences[:max_sentences])
    if len(truncated) > max_chars:
        truncated = truncated[:max_chars].rsplit(" ", 1)[0]
    return truncated


def truncate_excerpt(text: str | None) -> str | None:
    """Truncate to 500 chars at the nearest word boundary at or before the cap."""
    if not text:
        return None
    if len(text) <= 500:
        return text
    return text[:500].rsplit(" ", 1)[0]


# --- Metadata extraction ------------------------------------------------------


def _get_header(headers: list[dict], name: str) -> str | None:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def extract_metadata(msg: dict) -> dict:
    """
    Parse id, internalDate, and From/Subject headers from a raw Gmail message dict.

    Raises InvalidMetadataError(field_name) for any missing/invalid required field.
    """
    internal_date = msg.get("internalDate")
    if not internal_date:
        raise InvalidMetadataError("internalDate")
    try:
        internal_date_ms = int(internal_date)
    except (TypeError, ValueError):
        raise InvalidMetadataError("internalDate")
    if internal_date_ms == 0:
        raise InvalidMetadataError("internalDate")

    headers = msg.get("payload", {}).get("headers", [])

    from_header = _get_header(headers, "From")
    if not from_header or not from_header.strip():
        raise InvalidMetadataError("From")
    sender_name, sender_email = parseaddr(from_header)
    if not sender_email or "@" not in sender_email:
        raise InvalidMetadataError("From")

    subject = _get_header(headers, "Subject")
    if not subject or not subject.strip():
        raise InvalidMetadataError("Subject")

    received_at = (
        datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    return {
        "gmail_message_id": msg["id"],
        "sender_email": sender_email,
        "sender_name": sender_name or None,
        "subject": subject,
        "received_at": received_at,
    }


def _decode_body_part(part: dict) -> str | None:
    data = part.get("body", {}).get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            return None
    for sub in part.get("parts", []) or []:
        if sub.get("mimeType") == "text/plain":
            decoded = _decode_body_part(sub)
            if decoded:
                return decoded
    for sub in part.get("parts", []) or []:
        decoded = _decode_body_part(sub)
        if decoded:
            return decoded
    return None


def extract_body(msg: dict) -> str | None:
    """Decode and return the plain-text body of a raw Gmail message, or None if absent."""
    payload = msg.get("payload", {})
    return _decode_body_part(payload)


# --- Payload assembly ----------------------------------------------------------


def extract_payload(metadata: dict, classification: ClassificationResponse) -> DealPayload:
    """
    Map metadata + classification into a validated DealPayload.

    Raises SchemaValidationError(field_name) on any missing/out-of-range field.
    """
    if not classification.deal_summary or not classification.deal_summary.strip():
        raise SchemaValidationError("deal_summary")
    if classification.deal_category not in _DEAL_CATEGORIES:
        raise SchemaValidationError("deal_category")
    if not (0.0 <= classification.confidence_score <= 1.0):
        raise SchemaValidationError("confidence_score")

    return DealPayload(
        gmail_message_id=metadata["gmail_message_id"],
        sender_email=metadata["sender_email"],
        sender_name=metadata["sender_name"],
        subject=metadata["subject"],
        received_at=metadata["received_at"],
        deal_summary=truncate_summary(classification.deal_summary),
        deal_category=classification.deal_category,
        confidence_score=classification.confidence_score,
        raw_email_excerpt=truncate_excerpt(classification.raw_email_excerpt),
    )
