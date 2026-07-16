"""Unit tests for src/crm_logger/client.py — HubSpotClient."""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from crm_logger.client import HubSpotClient
from crm_logger.models import (
    HubSpot401Error,
    HubSpotMissingResourceIdError,
    HubSpotRateLimitError,
    HubSpotResponseError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client() -> HubSpotClient:
    return HubSpotClient(token="test-token")


def _mock_response(status: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.ok = status < 400
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# _call() — status-code routing
# ---------------------------------------------------------------------------

@patch("crm_logger.client.time.sleep")
def test_call_raises_401_error_without_sleeping(mock_sleep):
    client = _make_client()
    mock_resp = _mock_response(401)
    client._session.request = MagicMock(return_value=mock_resp)

    with pytest.raises(HubSpot401Error):
        client._call("GET", "/test")

    mock_sleep.assert_not_called()


@patch("crm_logger.client.time.sleep")
def test_call_raises_rate_limit_error_on_429(mock_sleep):
    client = _make_client()
    mock_resp = _mock_response(429)
    client._session.request = MagicMock(return_value=mock_resp)

    with pytest.raises(HubSpotRateLimitError):
        client._call("GET", "/test")

    mock_sleep.assert_called_once_with(0.1)


@patch("crm_logger.client.time.sleep")
def test_call_raises_response_error_on_5xx(mock_sleep):
    client = _make_client()
    mock_resp = _mock_response(500, text="Internal Server Error")
    client._session.request = MagicMock(return_value=mock_resp)

    with pytest.raises(HubSpotResponseError) as exc_info:
        client._call("GET", "/test")

    assert exc_info.value.status_code == 500


@patch("crm_logger.client.time.sleep")
def test_call_returns_json_on_success(mock_sleep):
    client = _make_client()
    mock_resp = _mock_response(200, json_body={"id": "abc"})
    client._session.request = MagicMock(return_value=mock_resp)

    result = client._call("GET", "/test")
    assert result == {"id": "abc"}


# ---------------------------------------------------------------------------
# _call() — rate-guard behaviour (T023)
# ---------------------------------------------------------------------------

@patch("crm_logger.client.time.sleep")
def test_call_sleeps_100ms_after_each_non_401_response(mock_sleep):
    client = _make_client()
    mock_resp = _mock_response(200, json_body={})
    client._session.request = MagicMock(return_value=mock_resp)

    client._call("GET", "/a")
    client._call("GET", "/b")
    client._call("GET", "/c")

    assert mock_sleep.call_count == 3
    for call in mock_sleep.call_args_list:
        assert call.args[0] == 0.1


@patch("crm_logger.client.time.sleep")
def test_call_count_increments_per_call(mock_sleep):
    client = _make_client()
    mock_resp = _mock_response(200, json_body={})
    client._session.request = MagicMock(return_value=mock_resp)

    assert client.call_count == 0
    client._call("GET", "/a")
    assert client.call_count == 1
    client._call("GET", "/b")
    assert client.call_count == 2


@patch("crm_logger.client.time.sleep")
def test_reset_call_count(mock_sleep):
    client = _make_client()
    mock_resp = _mock_response(200, json_body={})
    client._session.request = MagicMock(return_value=mock_resp)

    client._call("GET", "/a")
    client._call("GET", "/b")
    assert client.call_count == 2
    client.reset_call_count()
    assert client.call_count == 0


# ---------------------------------------------------------------------------
# search_contact (T011)
# ---------------------------------------------------------------------------

@patch("crm_logger.client.time.sleep")
def test_search_contact_found_returns_id(mock_sleep):
    client = _make_client()
    client._session.request = MagicMock(return_value=_mock_response(200, json_body={
        "results": [{"id": "42"}]
    }))
    result = client.search_contact("alice@example.com")
    assert result == "42"


@patch("crm_logger.client.time.sleep")
def test_search_contact_not_found_returns_none(mock_sleep):
    client = _make_client()
    client._session.request = MagicMock(return_value=_mock_response(200, json_body={
        "results": []
    }))
    result = client.search_contact("nobody@example.com")
    assert result is None


@patch("crm_logger.client.time.sleep")
def test_search_contact_multi_match_selects_lowest_id(mock_sleep):
    client = _make_client()
    client._session.request = MagicMock(return_value=_mock_response(200, json_body={
        "results": [{"id": "100"}, {"id": "42"}, {"id": "200"}]
    }))
    result = client.search_contact("dup@example.com")
    assert result == "42"


# ---------------------------------------------------------------------------
# upsert_contact (T012)
# ---------------------------------------------------------------------------

@patch("crm_logger.client.time.sleep")
def test_upsert_contact_finds_existing(mock_sleep):
    client = _make_client()
    search_resp = _mock_response(200, json_body={"results": [{"id": "99"}]})
    client._session.request = MagicMock(return_value=search_resp)

    result = client.upsert_contact("alice@example.com", "Alice", "Doe")
    assert result == "99"
    # Only one call was made (the search call returned an existing contact)
    assert client.call_count == 1


@patch("crm_logger.client.time.sleep")
def test_upsert_contact_creates_new(mock_sleep):
    client = _make_client()
    search_resp = _mock_response(200, json_body={"results": []})
    create_resp = _mock_response(201, json_body={"id": "77"})
    client._session.request = MagicMock(side_effect=[search_resp, create_resp])

    result = client.upsert_contact("new@example.com", "New", "User")
    assert result == "77"
    assert client.call_count == 2


# ---------------------------------------------------------------------------
# create_deal (T013)
# ---------------------------------------------------------------------------

@patch("crm_logger.client.time.sleep")
def test_create_deal_returns_id(mock_sleep):
    client = _make_client()
    client._session.request = MagicMock(return_value=_mock_response(201, json_body={"id": "deal-1"}))

    result = client.create_deal(
        dealname="Test deal",
        deal_category="rfp",
        confidence_score=0.9,
        deal_summary="A summary",
        received_date_ms=1704189600000,
        gmail_message_id="msg-abc",
        contact_id="c-1",
    )
    assert result == "deal-1"
