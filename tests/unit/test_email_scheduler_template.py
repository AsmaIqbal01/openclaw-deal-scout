"""Unit tests for email_scheduler.template.render_email() — T011."""
from __future__ import annotations

import pytest

from email_scheduler.template import _DEFAULT_TEMPLATE, render_email

_BASE = {
    "gmail_message_id": "msg_abc",
    "sender_email": "buyer@example.com",
    "sender_name": "Alice",
    "company_name": "Acme Ltd",
    "deal_summary": "Need 10 widgets urgently",
    "subject": "Original subject line",
}


class TestSubjectDerivation:
    def test_deal_summary_used_when_present(self):
        subject, _ = render_email(_BASE)
        assert subject == "Need 10 widgets urgently"

    def test_subject_field_used_when_deal_summary_absent(self):
        payload = {**_BASE, "deal_summary": None}
        subject, _ = render_email(payload)
        assert subject == "Original subject line"

    def test_hardcoded_fallback_when_both_absent(self):
        payload = {**_BASE, "deal_summary": None, "subject": None}
        subject, _ = render_email(payload)
        assert subject == "Following up on your enquiry"

    def test_whitespace_only_deal_summary_treated_as_absent(self):
        payload = {**_BASE, "deal_summary": "   "}
        subject, _ = render_email(payload)
        assert subject == "Original subject line"

    def test_whitespace_only_subject_treated_as_absent(self):
        payload = {**_BASE, "deal_summary": None, "subject": "  \t  "}
        subject, _ = render_email(payload)
        assert subject == "Following up on your enquiry"


class TestBodySubstitution:
    def test_recipient_name_appears_in_body(self):
        _, body = render_email(_BASE)
        assert "Alice" in body

    def test_recipient_name_absent_uses_there(self):
        payload = {**_BASE, "sender_name": None}
        _, body = render_email(payload)
        assert "there" in body

    def test_company_name_appears_in_body_when_present(self):
        _, body = render_email(_BASE)
        assert "Acme Ltd" in body

    def test_company_name_absent_no_spurious_text(self):
        payload = {**_BASE, "company_name": None}
        _, body = render_email(payload)
        assert "None" not in body
        assert "company_line" not in body

    def test_deal_summary_appears_in_body(self):
        _, body = render_email(_BASE)
        assert "Need 10 widgets urgently" in body

    def test_deal_summary_absent_subject_used_in_body(self):
        payload = {**_BASE, "deal_summary": None}
        _, body = render_email(payload)
        assert "Original subject line" in body


class TestCustomTemplate:
    def test_custom_template_string_overrides_default(self):
        _, body = render_email(_BASE, template_str="HELLO {recipient_name}")
        assert body == "HELLO Alice"

    def test_custom_template_loaded_from_file(self, tmp_path):
        tpl = tmp_path / "tpl.txt"
        tpl.write_text("Dear {recipient_name}, case: {deal_summary}", encoding="utf-8")
        subject, body = render_email(_BASE, template_path=str(tpl))
        assert "Alice" in body
        assert "Need 10 widgets urgently" in body

    def test_unreadable_template_file_falls_back_to_built_in(self):
        _, body = render_email(_BASE, template_path="/nonexistent/dir/tpl.txt")
        assert "Kind regards" in body

    def test_missing_placeholder_in_custom_template_silenced(self):
        _, body = render_email(_BASE, template_str="{unknown_key} {recipient_name}")
        assert "Alice" in body
        assert "{unknown_key}" not in body
