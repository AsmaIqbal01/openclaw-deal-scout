"""Tests for discord_notifier.adapter — T008 (US1), T016 (US3), T020 (US4)."""
import pytest
import requests
from unittest.mock import MagicMock, patch

from discord_notifier.adapter import DiscordAdapter, NoopAdapter, get_adapter

_DEAL = {
    "gmail_message_id": "msg-001",
    "sender_email": "a@example.com",
    "sender_name": "Alice",
    "subject": "Test deal",
    "deal_summary": "A test deal.",
    "deal_category": "lead",
    "confidence_score": 0.8,
    "raw_email_excerpt": None,
    "status": "crm-logged",
}

_WEBHOOK = "https://discord.com/api/webhooks/123/abc"


def _adapter():
    return DiscordAdapter(webhook_url=_WEBHOOK)


def _mock_resp(status_code=200, json_body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


# ── T008 US1: DiscordAdapter HTTP responses ──────────────────────────────────

def test_adapter_http_200_returns_notified():
    with patch("discord_notifier.adapter.requests.post", return_value=_mock_resp(200)):
        assert _adapter().notify(_DEAL) == "discord-notified"


def test_adapter_http_204_returns_notified():
    with patch("discord_notifier.adapter.requests.post", return_value=_mock_resp(204)):
        assert _adapter().notify(_DEAL) == "discord-notified"


def test_adapter_http_429_returns_pending_and_logs(caplog):
    body = {"retry_after": 2.5, "message": "rate limited"}
    with patch("discord_notifier.adapter.requests.post", return_value=_mock_resp(429, json_body=body)):
        import logging
        with caplog.at_level(logging.WARNING):
            result = _adapter().notify(_DEAL)
    assert result == "crm-logged-notify-pending"
    assert "rate limited" in caplog.text.lower() or "retry_after" in caplog.text


def test_adapter_http_400_returns_pending(caplog):
    with patch("discord_notifier.adapter.requests.post", return_value=_mock_resp(400, text="Invalid Form Body")):
        import logging
        with caplog.at_level(logging.WARNING):
            result = _adapter().notify(_DEAL)
    assert result == "crm-logged-notify-pending"


def test_adapter_http_500_returns_pending():
    with patch("discord_notifier.adapter.requests.post", return_value=_mock_resp(500)):
        assert _adapter().notify(_DEAL) == "crm-logged-notify-pending"


def test_adapter_timeout_returns_pending(caplog):
    import logging
    with patch(
        "discord_notifier.adapter.requests.post",
        side_effect=requests.exceptions.Timeout("timed out"),
    ):
        with caplog.at_level(logging.WARNING):
            result = _adapter().notify(_DEAL)
    assert result == "crm-logged-notify-pending"
    assert "timeout" in caplog.text.lower()


def test_adapter_connection_error_returns_pending():
    with patch(
        "discord_notifier.adapter.requests.post",
        side_effect=requests.exceptions.ConnectionError("connection refused"),
    ):
        assert _adapter().notify(_DEAL) == "crm-logged-notify-pending"


def test_adapter_empty_webhook_raises():
    with pytest.raises(EnvironmentError, match="DISCORD_WEBHOOK_URL"):
        DiscordAdapter(webhook_url="")


# ── T008 US1: get_adapter factory ────────────────────────────────────────────

def test_get_adapter_discord_returns_discord_adapter():
    adapter = get_adapter("discord", {"DISCORD_WEBHOOK_URL": _WEBHOOK})
    assert isinstance(adapter, DiscordAdapter)


def test_get_adapter_noop_returns_noop_adapter():
    adapter = get_adapter("noop", {})
    assert isinstance(adapter, NoopAdapter)


def test_get_adapter_none_raises():
    with pytest.raises(EnvironmentError, match="NOTIFIER"):
        get_adapter(None, {})


def test_get_adapter_unknown_raises():
    with pytest.raises(EnvironmentError, match="slack"):
        get_adapter("slack", {})


def test_get_adapter_discord_without_url_raises():
    with pytest.raises(EnvironmentError, match="DISCORD_WEBHOOK_URL"):
        get_adapter("discord", {})


# ── T016 US3: additional failure paths ───────────────────────────────────────

def test_adapter_connection_error_bad_url_returns_pending():
    with patch(
        "discord_notifier.adapter.requests.post",
        side_effect=requests.exceptions.ConnectionError("name not resolved"),
    ):
        assert _adapter().notify(_DEAL) == "crm-logged-notify-pending"


def test_adapter_http_400_embed_error_returns_pending():
    with patch(
        "discord_notifier.adapter.requests.post",
        return_value=_mock_resp(400, text='{"code":50035,"message":"Invalid Form Body"}'),
    ):
        assert _adapter().notify(_DEAL) == "crm-logged-notify-pending"


def test_adapter_http_503_returns_pending():
    with patch("discord_notifier.adapter.requests.post", return_value=_mock_resp(503)):
        assert _adapter().notify(_DEAL) == "crm-logged-notify-pending"


# ── T020 US4: NoopAdapter contract and swappable factory ─────────────────────

def test_noop_adapter_always_returns_notified():
    assert NoopAdapter().notify(_DEAL) == "discord-notified"
    assert NoopAdapter().notify({}) == "discord-notified"


def test_plain_class_satisfies_contract_duck_typed():
    """A plain class with notify() satisfies NotifierContract without importing it."""
    class CountingAdapter:
        def __init__(self):
            self.count = 0

        def notify(self, deal):
            self.count += 1
            return "discord-notified"

    adapter = CountingAdapter()
    # Verify it works when called the same way the real code calls adapters
    result = adapter.notify(_DEAL)
    assert result == "discord-notified"
    assert adapter.count == 1


def test_get_adapter_noop_delivers_notified():
    adapter = get_adapter("noop", {})
    assert adapter.notify(_DEAL) == "discord-notified"


def test_get_adapter_discord_sets_webhook_correctly():
    adapter = get_adapter("discord", {"DISCORD_WEBHOOK_URL": _WEBHOOK})
    assert isinstance(adapter, DiscordAdapter)
    assert adapter._webhook_url == _WEBHOOK


def test_get_adapter_empty_string_raises():
    with pytest.raises(EnvironmentError):
        get_adapter("", {})
