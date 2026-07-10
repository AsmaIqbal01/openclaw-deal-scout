"""
T019 — Unit tests for gmail_intake.classifier.classify().

Tests are written against the classify() interface defined in tasks.md T014.
They mock at the genai.GenerativeModel level and patch time.sleep to avoid
actual delays during retry backoff.

Assumes classifier.py uses:
  import time
  import google.generativeai as genai
"""
from unittest.mock import MagicMock, call, patch

import google.api_core.exceptions
import pytest

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


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("gmail_intake.classifier.time.sleep")
@patch("gmail_intake.classifier.genai.GenerativeModel")
def test_classify_429_retry_schedule(mock_model_cls, mock_sleep):
    """429 three times then success → 4 total calls; sleep delays are 10/30/60 s."""
    mock_model = MagicMock()
    mock_model_cls.return_value = mock_model
    mock_model.generate_content.side_effect = [
        google.api_core.exceptions.ResourceExhausted("429"),
        google.api_core.exceptions.ResourceExhausted("429"),
        google.api_core.exceptions.ResourceExhausted("429"),
        _mock_response(_VALID_JSON),
    ]

    result = classify(_REQUEST, api_key="test-key")

    assert mock_model.generate_content.call_count == 4
    assert mock_sleep.call_args_list == [call(10), call(30), call(60)]
    assert isinstance(result, ClassificationResponse)
    assert result.is_deal is True


@patch("gmail_intake.classifier.time.sleep")
@patch("gmail_intake.classifier.genai.GenerativeModel")
def test_classify_429_exhausted(mock_model_cls, mock_sleep):
    """429 four consecutive times → RateLimitExhaustedError after 4 attempts."""
    mock_model = MagicMock()
    mock_model_cls.return_value = mock_model
    mock_model.generate_content.side_effect = [
        google.api_core.exceptions.ResourceExhausted("429"),
        google.api_core.exceptions.ResourceExhausted("429"),
        google.api_core.exceptions.ResourceExhausted("429"),
        google.api_core.exceptions.ResourceExhausted("429"),
    ]

    with pytest.raises(RateLimitExhaustedError):
        classify(_REQUEST, api_key="test-key")

    assert mock_model.generate_content.call_count == 4


@patch("gmail_intake.classifier.time.sleep")
@patch("gmail_intake.classifier.genai.GenerativeModel")
def test_classify_non_429_no_retry(mock_model_cls, mock_sleep):
    """Non-429 error (500) → ClassificationError raised after exactly 1 call, no sleep."""
    mock_model = MagicMock()
    mock_model_cls.return_value = mock_model
    mock_model.generate_content.side_effect = [
        google.api_core.exceptions.InternalServerError("500"),
    ]

    with pytest.raises(ClassificationError):
        classify(_REQUEST, api_key="test-key")

    assert mock_model.generate_content.call_count == 1
    mock_sleep.assert_not_called()


@patch("gmail_intake.classifier.genai.GenerativeModel")
def test_classify_returns_classification_response(mock_model_cls):
    """Valid Gemini response → correctly parsed ClassificationResponse dataclass."""
    mock_model = MagicMock()
    mock_model_cls.return_value = mock_model
    mock_model.generate_content.return_value = _mock_response(_VALID_JSON)

    result = classify(_REQUEST, api_key="test-key")

    assert isinstance(result, ClassificationResponse)
    assert result.is_deal is True
    assert result.confidence_score == 0.9
    assert result.deal_category == "lead"
    assert result.deal_summary == "A new lead enquiry."
    assert result.raw_email_excerpt == "We are interested in your services."
