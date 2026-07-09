from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class StateStoreReadError(Exception):
    """State store file exists but cannot be read or parsed as valid JSON."""


class ConcurrentInvocationError(Exception):
    """A second invocation attempted to acquire the exclusive state store lock."""


class SchemaValidationError(Exception):
    """A required DealPayload field is missing or fails its validation rule."""


class AuthError(Exception):
    """Gmail OAuth token refresh failed; polling cannot proceed."""


class RateLimitExhaustedError(Exception):
    """Gemini 429 rate limit: all 3 retries exhausted."""


class ClassificationError(Exception):
    """Non-429 Gemini API error; no retry attempted."""


class InvalidMetadataError(Exception):
    """
    A required Gmail header or metadata field is absent, empty, or invalid.
    Pass the field name as the exception message, e.g. InvalidMetadataError("internalDate").
    """


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

DealCategory = Literal["lead", "partnership_inquiry", "vendor_offer", "rfq", "other"]

ProcessedMessageOutcome = Literal[
    "deal_extracted",
    "not_a_deal",
    "schema_error",
    "rate_limited",
    "body_absent",
    "invalid_metadata",
    "classification_error",
]


@dataclass
class DealPayload:
    """Structured output produced for each confirmed deal."""
    gmail_message_id:  str                    # Non-empty; idempotency key
    sender_email:      str                    # Non-empty; must contain '@'
    sender_name:       str | None             # None if absent from From header
    subject:           str                    # Non-empty
    received_at:       str                    # ISO 8601 UTC from Gmail internalDate
    deal_summary:      str                    # 1–2 sentences; max 500 chars (FR-011)
    deal_category:     DealCategory           # Exactly one of 5 enum values
    confidence_score:  float                  # 0.0–1.0 inclusive
    raw_email_excerpt: str | None             # Max 500 chars; None if body absent


@dataclass
class ProcessedMessage:
    """One state store entry per email evaluated by check_new_deals."""
    gmail_message_id: str
    processed_at:     str                     # ISO 8601 UTC; time of atomic write
    outcome:          ProcessedMessageOutcome


@dataclass
class ClassificationRequest:
    """Inputs passed to the Gemini classifier for each email."""
    subject:        str
    sender_email:   str
    sender_name:    str | None
    body_excerpt:   str | None                # Capped at 8,000 chars; None if body absent
    target_segment: str = "UK micro-business, fewer than 10 employees"


@dataclass
class ClassificationResponse:
    """JSON schema that Gemini returns, enforced via response_schema."""
    is_deal:           bool
    confidence_score:  float                  # 0.0–1.0
    deal_category:     DealCategory | None    # None when is_deal=False
    deal_summary:      str | None             # None when is_deal=False
    raw_email_excerpt: str | None             # None when is_deal=False; max 500 chars


@dataclass
class StateStore:
    """Top-level structure of processed_ids.json."""
    last_poll_time: str | None                # ISO 8601 UTC | None on first run
    messages:       list[ProcessedMessage] = field(default_factory=list)
