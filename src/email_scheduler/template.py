"""render_email — subject and body rendering with per-field fallbacks."""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_TEMPLATE = """\
Hi {recipient_name},

Thank you for your message.{company_line}

{deal_summary}

I would be happy to discuss this further. Please feel free to reach out at your convenience.

Kind regards,
OpenClaw Team"""


def _is_present(value: object) -> bool:
    """Return True if value is non-None, non-empty, and non-whitespace-only."""
    if value is None:
        return False
    return bool(str(value).strip())


def _load_template(template_path: str | None) -> str:
    """Load template from file; fall back to built-in on any error."""
    if not template_path:
        return _DEFAULT_TEMPLATE
    try:
        return Path(template_path).read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning(
            "template: could not read EMAIL_TEMPLATE_PATH '%s' (%s) — using built-in",
            template_path,
            exc,
        )
        return _DEFAULT_TEMPLATE


def render_email(
    deal_payload: dict,
    template_str: str | None = None,
    template_path: str | None = None,
) -> tuple[str, str]:
    """
    Render (subject, body) for a deal payload.

    Subject fallback order (FR-009):
      1. deal_summary (non-empty)
      2. subject field (non-empty)
      3. "Following up on your enquiry"

    Body field fallbacks:
      recipient_name absent → "there"
      company_name absent   → empty company_line (line effectively omitted)
      deal_summary absent   → subject value (already derived above)
    """
    if template_str is None:
        template_str = _load_template(template_path)

    # --- subject ---
    deal_summary_raw = deal_payload.get("deal_summary")
    subject_raw = deal_payload.get("subject")

    if _is_present(deal_summary_raw):
        subject = str(deal_summary_raw).strip()
    elif _is_present(subject_raw):
        subject = str(subject_raw).strip()
    else:
        subject = "Following up on your enquiry"

    # --- body substitution values ---
    recipient_name_raw = deal_payload.get("sender_name") or deal_payload.get("recipient_name")
    company_name_raw = deal_payload.get("company_name")

    recipient_name = (
        str(recipient_name_raw).strip() if _is_present(recipient_name_raw) else "there"
    )
    company_name = (
        str(company_name_raw).strip() if _is_present(company_name_raw) else ""
    )
    company_line = f" We'd love to help {company_name}." if company_name else ""
    deal_summary_body = (
        str(deal_summary_raw).strip() if _is_present(deal_summary_raw) else subject
    )

    subs: dict[str, str] = defaultdict(
        str,
        {
            "recipient_name": recipient_name,
            "company_name": company_name,
            "company_line": company_line,
            "deal_summary": deal_summary_body,
            "subject": subject,
        },
    )

    try:
        body = template_str.format_map(subs)
    except Exception as exc:
        logger.warning("template: format_map failed (%s) — using raw template", exc)
        body = template_str

    return subject, body
