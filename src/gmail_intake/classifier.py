import json
import logging
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

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

_PROMPT_TEMPLATE = """You are a business deal classifier for an automated email assistant serving {target_segment}.

Analyse the following email and determine whether it represents a genuine business deal opportunity — such as a sales lead, partnership inquiry, vendor quote request, or RFQ — directed at this business.

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

---
STRICT REJECTION RULES (check before scoring confidence):

Classify is_deal=false immediately if ANY of these match:
- Sender address contains: noreply@, newsletters-noreply@, digest@, no-reply@ AND the email contains no specific actionable opportunity (no named counterparty, no contact details, no concrete terms/price)
- Email body contains the word 'unsubscribe' AND is a mass newsletter/content digest (news roundup, article digest, promotional roundup)
- Email is a broadcast/digest of NEWS or CONTENT (LinkedIn Newsletter, Substack, "roundup", "weekly news") with no specific transactional opportunity
- Generic marketing/promo email with no specific counterparty, product, price, or contact info

HARD BLOCK LIST (always confidence_score=0.0, is_deal=false, no exceptions, skip remaining analysis):
- Newsletters/content emails from: Anthropic, GitHub, LinkedIn, Substack, Medium (by sender domain or brand name in From/subject)
- Promotional/marketing emails (discounts, sales, "% off", course/product promos)
- Brand offer emails (a company pitching its own product/service to a mass list, not a specific counterparty pitching a deal to this recipient)
- Automated *system/service* notification emails with no business-lead content (account alerts, deployment/build status, app "tips", group-join confirmations, social network invitations)
- Any email containing the word 'unsubscribe'

Do NOT reject an email solely because it is auto-generated (e.g. a saved-search or listing alert). If an automated email surfaces a SPECIFIC actionable business opportunity — a named counterparty, contact details (phone/email), and concrete terms (price, product, property) — it is NOT covered by the "automated notification" block above; treat it like any other lead and score it on its merits instead of auto-rejecting it.

If a rejection rule matches, set is_deal=false and confidence_score=0.0, skip remaining analysis.

EXAMPLE MESSAGES — use these as ground truth for classification:

❌ NOT A DEAL (is_deal=false, confidence=0.0):
Subject: 'GenAI Works is offering micro-businesses AI tools to feature their products'
From: newsletters-noreply@linkedin.com
Reason: mass LinkedIn newsletter, unsubscribe link present, no direct recipient mention, no specific counterparty or terms

❌ NOT A DEAL (is_deal=false, confidence=0.0):
Subject: 'Weekly AI News Roundup — top 10 stories'
From: digest@spideybot.discord
Reason: automated news/content digest, not a business opportunity, no counterparty or terms

✅ IS A DEAL (is_deal=true, confidence>=0.85):
Subject: 'Partnership inquiry for your AI automation services'
From: john.smith@acmeltd.co.uk
Body: 'Hi, I found your profile and I'm looking for someone to automate our invoicing workflow. Can we get on a call this week?'
Reason: direct, personalized, names a specific need, sent to this recipient specifically

✅ IS A DEAL (is_deal=true, confidence>=0.85):
Subject: 'New Property Alert — 10 Marla House for Sale in DHA Phase 6, Lahore'
From: alerts@zameen.com
Body: 'A new property matching your saved search has been listed... Seller Contact: Name: Usman Afzal Malik, Phone: 0300-1234567... Owner motivated to sell quickly.'
Reason: automated listing alert, but names a specific property, price, and seller with contact details — an actionable lead for a real estate business, not generic marketing
---

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
    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(request)
    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
    )

    attempts = 1 + len(_RETRY_DELAYS_SECONDS)
    for attempt in range(attempts):
        try:
            response = client.models.generate_content(
                model=_MODEL_NAME,
                contents=prompt,
                config=config,
            )
        except genai_errors.ClientError as exc:
            if exc.code == 429:
                if attempt < len(_RETRY_DELAYS_SECONDS):
                    time.sleep(_RETRY_DELAYS_SECONDS[attempt])
                    continue
                logger.warning("classification rate-limited — skipped")
                raise RateLimitExhaustedError("Gemini rate limit exhausted after 3 retries") from exc
            logger.warning("classification failed: %d/%s", exc.code, exc)
            raise ClassificationError(str(exc)) from exc
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
