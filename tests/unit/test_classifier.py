"""
T019 — Unit tests for gmail_intake.classifier.classify().

Tests are written against the classify() interface defined in tasks.md T014.
They mock at the genai.Client level and patch time.sleep to avoid actual
delays during retry backoff.

Assumes classifier.py uses:
  import time
  from google import genai
  from google.genai import errors as genai_errors
"""
from unittest.mock import MagicMock, call, patch

import pytest
from google.genai import errors as genai_errors

from gmail_intake.classifier import classify
from gmail_intake.models import (
    ClassificationError,
    ClassificationRequest,
    ClassificationResponse,
    RateLimitExhaustedError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REQUEST = ClassificationRequest(
    subject="Business Proposal",
    sender_email="vendor@example.com",
    sender_name="Vendor Corp",
    body_excerpt="We are interested in your services.",
)

_VALID_JSON = (
    '{"is_deal": true, "confidence_score": 0.9, "deal_category": "lead",'
    ' "deal_summary": "A new lead enquiry.", "raw_email_excerpt": "We are interested in your services."}'
)

_ERR_429 = genai_errors.ClientError(429, {})
_ERR_500 = genai_errors.ServerError(500, {})


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("gmail_intake.classifier.time.sleep")
@patch("gmail_intake.classifier.genai.Client")
def test_classify_429_retry_schedule(mock_client_cls, mock_sleep):
    """429 three times then success → 4 total calls; sleep delays are 10/30/60 s."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _ERR_429,
        _ERR_429,
        _ERR_429,
        _mock_response(_VALID_JSON),
    ]

    result = classify(_REQUEST, api_key="test-key")

    assert mock_client.models.generate_content.call_count == 4
    assert mock_sleep.call_args_list == [call(10), call(30), call(60)]
    assert isinstance(result, ClassificationResponse)
    assert result.is_deal is True


@patch("gmail_intake.classifier.time.sleep")
@patch("gmail_intake.classifier.genai.Client")
def test_classify_429_exhausted(mock_client_cls, mock_sleep):
    """429 four consecutive times → RateLimitExhaustedError after 4 attempts."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [
        _ERR_429,
        _ERR_429,
        _ERR_429,
        _ERR_429,
    ]

    with pytest.raises(RateLimitExhaustedError):
        classify(_REQUEST, api_key="test-key")

    assert mock_client.models.generate_content.call_count == 4


@patch("gmail_intake.classifier.time.sleep")
@patch("gmail_intake.classifier.genai.Client")
def test_classify_non_429_no_retry(mock_client_cls, mock_sleep):
    """Non-429 error (500) → ClassificationError raised after exactly 1 call, no sleep."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = [_ERR_500]

    with pytest.raises(ClassificationError):
        classify(_REQUEST, api_key="test-key")

    assert mock_client.models.generate_content.call_count == 1
    mock_sleep.assert_not_called()


@patch("gmail_intake.classifier.genai.Client")
def test_classify_returns_classification_response(mock_client_cls):
    """Valid Gemini response → correctly parsed ClassificationResponse dataclass."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(_VALID_JSON)

    result = classify(_REQUEST, api_key="test-key")

    assert isinstance(result, ClassificationResponse)
    assert result.is_deal is True
    assert result.confidence_score == 0.9
    assert result.deal_category == "lead"
    assert result.deal_summary == "A new lead enquiry."
    assert result.raw_email_excerpt == "We are interested in your services."


@patch("gmail_intake.classifier.genai.Client")
def test_newsletter_rejected(mock_client_cls):
    """Newsletter-style email (noreply sender + 'unsubscribe' body) → is_deal=False, confidence_score=0.0."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(
        '{"is_deal": false, "confidence_score": 0.0, "deal_category": null,'
        ' "deal_summary": null, "raw_email_excerpt": null}'
    )
    request = ClassificationRequest(
        subject="Your Weekly Digest",
        sender_email="newsletters-noreply@linkedin.com",
        sender_name="LinkedIn",
        body_excerpt="Top stories this week... Click here to unsubscribe.",
    )

    result = classify(request, api_key="test-key")

    assert result.is_deal is False
    assert result.confidence_score == 0.0


@patch("gmail_intake.classifier.genai.Client")
def test_discord_digest_rejected(mock_client_cls):
    """Automated digest email (digest@ sender, no personalized context) → is_deal=False, confidence_score=0.0."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(
        '{"is_deal": false, "confidence_score": 0.0, "deal_category": null,'
        ' "deal_summary": null, "raw_email_excerpt": null}'
    )
    request = ClassificationRequest(
        subject="Weekly AI News Roundup — top 10 stories",
        sender_email="digest@spideybot.discord",
        sender_name="SpideyBot Digest",
        body_excerpt="Top stories from your servers today. Read more on our blog.",
    )

    result = classify(request, api_key="test-key")

    assert result.is_deal is False
    assert result.confidence_score == 0.0


@patch("gmail_intake.classifier.genai.Client")
def test_direct_inquiry_passes(mock_client_cls):
    """Personalized partnership inquiry from a named individual → is_deal=True, confidence_score>=0.85."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = _mock_response(
        '{"is_deal": true, "confidence_score": 0.9, "deal_category": "partnership_inquiry",'
        ' "deal_summary": "Prospect wants to automate their invoicing workflow.",'
        ' "raw_email_excerpt": "I am looking for someone to automate our invoicing workflow."}'
    )
    request = ClassificationRequest(
        subject="Partnership inquiry for your AI automation services",
        sender_email="john.smith@acmeltd.co.uk",
        sender_name="John Smith",
        body_excerpt="Hi, I found your profile and I'm looking for someone to automate our invoicing workflow. Can we get on a call this week?",
    )

    result = classify(request, api_key="test-key")

    assert result.is_deal is True
    assert result.confidence_score >= 0.85
