"""
T023 — Unit tests for extractor.py: truncate_summary, truncate_excerpt, extract_payload.
FR-011 sentence boundary test cases from specs/001-gmail-intake/research.md Decision 8.
"""
import pytest

from gmail_intake.extractor import (
    extract_metadata,
    extract_payload,
    truncate_excerpt,
    truncate_summary,
)
from gmail_intake.models import (
    ClassificationResponse,
    InvalidMetadataError,
    SchemaValidationError,
)

# ---------------------------------------------------------------------------
# truncate_summary — FR-011 sentence boundary
# ---------------------------------------------------------------------------


def test_truncate_summary_two_sentences():
    """No split at Dr. — 'Hello Dr. Smith.' is one sentence."""
    result = truncate_summary("Hello Dr. Smith. This is a deal.")
    assert result == "Hello Dr. Smith. This is a deal."


def test_truncate_summary_uk_acronym():
    """No split within U.K. — both sentences preserved."""
    result = truncate_summary("We operate in the U.K. Our offer stands.")
    assert result == "We operate in the U.K. Our offer stands."


def test_truncate_summary_cap_at_two():
    """Third sentence is dropped."""
    result = truncate_summary("Lead received. Details follow. More info later.")
    assert result == "Lead received. Details follow."


def test_truncate_summary_500_char_cap():
    """When two sentences exceed 500 chars, truncate at nearest word boundary."""
    sentence = "This is a fairly long sentence with many words that will push the total " * 4
    text = sentence + ". " + sentence + "."
    result = truncate_summary(text)
    assert len(result) <= 500
    assert not result.endswith(" ")  # ends at a word boundary


def test_truncate_summary_mr_jones():
    """No split at Mr. or Ms. — exactly two sentences returned."""
    result = truncate_summary("Mr. Jones confirmed. Ms. Lee agreed. Next steps follow.")
    assert result == "Mr. Jones confirmed. Ms. Lee agreed."


# ---------------------------------------------------------------------------
# truncate_excerpt
# ---------------------------------------------------------------------------


def test_truncate_excerpt_under_500():
    text = "Short excerpt."
    assert truncate_excerpt(text) == text


def test_truncate_excerpt_over_500():
    text = ("word " * 120).rstrip()  # > 500 chars
    result = truncate_excerpt(text)
    assert result is not None
    assert len(result) <= 500
    assert not result.endswith(" ")


def test_truncate_excerpt_none():
    assert truncate_excerpt(None) is None


def test_truncate_excerpt_empty():
    assert truncate_excerpt("") is None


# ---------------------------------------------------------------------------
# extract_payload
# ---------------------------------------------------------------------------

_META = {
    "gmail_message_id": "abc123",
    "sender_email": "vendor@example.com",
    "sender_name": "Vendor Corp",
    "subject": "Business Proposal",
    "received_at": "2026-07-10T12:00:00Z",
}

_CLASSIFICATION = ClassificationResponse(
    is_deal=True,
    confidence_score=0.9,
    deal_category="lead",
    deal_summary="A new lead enquiry.",
    raw_email_excerpt="We are interested in your services.",
)


def test_extract_payload_schema_error_missing_required():
    """deal_summary=None raises SchemaValidationError."""
    bad = ClassificationResponse(
        is_deal=True,
        confidence_score=0.9,
        deal_category="lead",
        deal_summary=None,
        raw_email_excerpt=None,
    )
    with pytest.raises(SchemaValidationError):
        extract_payload(_META, bad)


def test_extract_payload_confidence_out_of_range():
    """confidence_score outside [0.0, 1.0] raises SchemaValidationError."""
    bad = ClassificationResponse(
        is_deal=True,
        confidence_score=1.5,
        deal_category="lead",
        deal_summary="Valid summary.",
        raw_email_excerpt=None,
    )
    with pytest.raises(SchemaValidationError):
        extract_payload(_META, bad)


def test_extract_payload_valid():
    """Happy path: all fields are mapped and DealPayload is returned."""
    payload = extract_payload(_META, _CLASSIFICATION)
    assert payload.gmail_message_id == "abc123"
    assert payload.sender_email == "vendor@example.com"
    assert payload.sender_name == "Vendor Corp"
    assert payload.subject == "Business Proposal"
    assert payload.received_at == "2026-07-10T12:00:00Z"
    assert payload.deal_summary == "A new lead enquiry."
    assert payload.deal_category == "lead"
    assert payload.confidence_score == 0.9
    assert payload.raw_email_excerpt == "We are interested in your services."


# ---------------------------------------------------------------------------
# extract_metadata — SC-004 #7 missing header tests (T031)
# ---------------------------------------------------------------------------


def test_missing_from_header():
    """SC-004 #7: absent From header raises InvalidMetadataError."""
    msg = {
        "id": "abc",
        "internalDate": "1720000000000",
        "payload": {"headers": [{"name": "Subject", "value": "Hello"}]},
    }
    with pytest.raises(InvalidMetadataError):
        extract_metadata(msg)


def test_missing_subject_header():
    """SC-004 #7: absent Subject header raises InvalidMetadataError."""
    msg = {
        "id": "abc",
        "internalDate": "1720000000000",
        "payload": {"headers": [{"name": "From", "value": "vendor@example.com"}]},
    }
    with pytest.raises(InvalidMetadataError):
        extract_metadata(msg)
