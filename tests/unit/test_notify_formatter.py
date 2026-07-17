"""Tests for discord_notifier.formatter — T006."""
from discord_notifier.formatter import format_embed

_BASE_DEAL = {
    "gmail_message_id": "msg-001",
    "sender_email": "jane@example.com",
    "sender_name": "Jane Smith",
    "subject": "Partnership inquiry",
    "received_at": "2026-07-17T09:00:00Z",
    "deal_summary": "Jane wants to discuss a joint venture.",
    "deal_category": "partnership_inquiry",
    "confidence_score": 0.87,
    "raw_email_excerpt": None,
    "status": "crm-logged",
}


def _embed(deal=None):
    return format_embed(deal or _BASE_DEAL)["embeds"][0]


# T1: Happy path — all fields present → correct embed structure and field values
def test_format_embed_happy_path():
    emb = _embed()
    assert emb["title"] == "Partnership inquiry"
    assert emb["description"] == "Jane wants to discuss a joint venture."
    fields = {f["name"]: f["value"] for f in emb["fields"]}
    assert fields["From"] == "Jane Smith <jane@example.com>"
    assert fields["Category"] == "partnership_inquiry"
    assert fields["Confidence"] == "87%"
    assert all(f["inline"] is True for f in emb["fields"])


# T2: sender_name=None → From value is email only (no "None" prefix)
def test_format_embed_null_sender_name():
    deal = {**_BASE_DEAL, "sender_name": None}
    emb = _embed(deal)
    fields = {f["name"]: f["value"] for f in emb["fields"]}
    assert fields["From"] == "jane@example.com"
    assert "None" not in fields["From"]


# T3: deal_summary empty string → description is "(no summary)"
def test_format_embed_empty_summary():
    deal = {**_BASE_DEAL, "deal_summary": ""}
    emb = _embed(deal)
    assert emb["description"] == "(no summary)"


# T4: Subject exactly 256 chars → no truncation
def test_format_embed_subject_at_limit():
    subject = "A" * 256
    deal = {**_BASE_DEAL, "subject": subject}
    emb = _embed(deal)
    assert len(emb["title"]) == 256
    assert not emb["title"].endswith("...")


# T5: Subject 257 chars → truncated to 253 + "..." = 256 chars total
def test_format_embed_subject_over_limit():
    subject = "B" * 257
    deal = {**_BASE_DEAL, "subject": subject}
    emb = _embed(deal)
    assert len(emb["title"]) == 256
    assert emb["title"].endswith("...")
    assert emb["title"] == "B" * 253 + "..."


# T6: confidence_score=0.875 → "88%" (rounded)
def test_format_embed_confidence_rounded():
    deal = {**_BASE_DEAL, "confidence_score": 0.875}
    emb = _embed(deal)
    fields = {f["name"]: f["value"] for f in emb["fields"]}
    assert fields["Confidence"] == "88%"


# T7: confidence_score=0.0 → "0%"
def test_format_embed_zero_confidence():
    deal = {**_BASE_DEAL, "confidence_score": 0.0}
    emb = _embed(deal)
    fields = {f["name"]: f["value"] for f in emb["fields"]}
    assert fields["Confidence"] == "0%"
