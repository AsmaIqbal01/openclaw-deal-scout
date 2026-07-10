import json
import logging
import time

import google.api_core.exceptions
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from gmail_intake.models import (
    ClassificationError,
    ClassificationRequest,
    ClassificationResponse,
    RateLimitExhaustedError,
)

logger = logging.getLogger(__name__)

_MODEL_NAME = "gemini-2.5-flash"
_RETRY_DELAYS_SECONDS = (10, 30, 60)  # 1 initial attempt + 3 retries = 4 total

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_deal": {"type": "boolean"},
        "confidence_score": {"type": "number"},
        "deal_category": {"type": "string", "nullable": True},
        "deal_summary": {"type": "string", "nullable": True},
        "raw_email_excerpt": {"type": "string", "nullable": True},
    },
    "required": [
        "is_deal",
        "confidence_score",
        "deal_category",
        "deal_summary",
        "raw_email_excerpt",
    ],
}

_PROMPT_TEMPLATE = """You are a business deal classifier for an automated email assistant serving UK micro-businesses (fewer than 10 employees).

Analyse the following email and determine whether it represents a genuine business deal opportunity — such as a sales lead, partnership inquiry, vendor quote request, or RFQ — directed at a UK micro-business.

Email details:
Subject: {subject}
Sender: {sender_name_or_anonymous} <{sender_email}>
Body:
{body_excerpt}

Target segment: {target_segment}

Classification rules:
1. Set is_deal=true ONLY for genuine business opportunities (leads, inquiries, partnership offers, vendor quotes, RFQs).
2. Set is_deal=false for: newsletters, marketing emails, spam, personal emails, automated notifications, transactional emails, and any email not directly relevant to business development.
3. confidence_score must reflect your certainty: 1.0 = certain, 0.5 = borderline, 0.0 = definitely not a deal.
4. If is_deal=false OR confidence_score < 0.5, set deal_category, deal_summary, and raw_email_excerpt to null.
5. deal_summary must be exactly 1-2 sentences describing the opportunity. No more.
6. raw_email_excerpt must be a verbatim short excerpt from the body (max 500 characters, ending at a word boundary) most relevant to the deal. Not a summary — a direct quote.
7. deal_category must be exactly one of: lead, partnership_inquiry, vendor_offer, rfq, other.
8. All five fields are required in your response even when is_deal=false.

Respond with a JSON object only. No prose. No markdown fences.
"""


def _build_prompt(request: ClassificationRequest) -> str:
    return _PROMPT_TEMPLATE.format(
        subject=request.subject,
        sender_name_or_anonymous=request.sender_name or "(no name given)",
        sender_email=request.sender_email,
        body_excerpt=request.body_excerpt or "(no body)",
        target_segment=request.target_segment,
    )


def classify(request: ClassificationRequest, api_key: str) -> ClassificationResponse:
    """
    Send an email to Gemini for deal classification.

    Retries on HTTP 429 (ResourceExhausted) with delays 10s / 30s / 60s
    (1 initial + 3 retries = 4 total attempts). Raises RateLimitExhaustedError
    if all retries are exhausted. Any non-429 error raises ClassificationError
    immediately, with no retry.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=_MODEL_NAME,
        generation_config=GenerationConfig(
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        ),
    )
    prompt = _build_prompt(request)

    attempts = 1 + len(_RETRY_DELAYS_SECONDS)
    for attempt in range(attempts):
        try:
            response = model.generate_content(prompt)
        except google.api_core.exceptions.ResourceExhausted as exc:
            if attempt < len(_RETRY_DELAYS_SECONDS):
                time.sleep(_RETRY_DELAYS_SECONDS[attempt])
                continue
            logger.warning("classification rate-limited — skipped")
            raise RateLimitExhaustedError("Gemini rate limit exhausted after 3 retries") from exc
        except Exception as exc:
            logger.warning("classification failed: %s/%s", type(exc).__name__, exc)
            raise ClassificationError(str(exc)) from exc
        else:
            try:
                data = json.loads(response.text)
                return ClassificationResponse(
                    is_deal=data["is_deal"],
                    confidence_score=data["confidence_score"],
                    deal_category=data.get("deal_category"),
                    deal_summary=data.get("deal_summary"),
                    raw_email_excerpt=data.get("raw_email_excerpt"),
                )
            except Exception as exc:
                logger.warning("classification failed: response_parse_error/%s", exc)
                raise ClassificationError(f"failed to parse Gemini response: {exc}") from exc

    # Unreachable, but satisfies type checkers.
    raise RateLimitExhaustedError("Gemini rate limit exhausted after 3 retries")
