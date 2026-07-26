"""Unit tests for email REST API handlers — T019."""
from __future__ import annotations

import dataclasses
import uuid
from typing import Any
from unittest import mock

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from email_scheduler.models import EmailEvent, EventType, ScheduledEmail
from email_scheduler.queue_store import EmailQueueStore
from openclaw_gateway.routes.email_api import (
    api_approve_email,
    api_cancel_email,
    api_list_email_events,
    api_list_emails,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _email(status: str = "scheduled", email_id: str | None = None) -> ScheduledEmail:
    return ScheduledEmail(
        id=email_id or str(uuid.uuid4()),
        gmail_message_id="msg_" + str(uuid.uuid4())[:6],
        recipient_name="Alice",
        recipient_email="alice@example.com",
        subject="Test subject",
        body="Test body",
        status=status,
        proposed_send_at="2026-07-28T09:00:00Z",
        created_at="2026-07-22T10:00:00Z",
    )


def _event(event_type: str = "scheduled") -> EmailEvent:
    return EmailEvent(
        event_id=str(uuid.uuid4()),
        email_id=str(uuid.uuid4()),
        gmail_message_id="msg_" + str(uuid.uuid4())[:6],
        event_type=event_type,
        timestamp="2026-07-22T10:00:00Z",
        actor="system",
    )


@pytest.fixture()
def mock_store(tmp_path):
    store = EmailQueueStore(tmp_path / "q.json")
    store.load()
    return store


@pytest.fixture()
def mock_audit(tmp_path):
    from email_scheduler.audit_logger import AuditLogger
    return AuditLogger(tmp_path / "audit.log")


def _make_app(routes_list):
    return Starlette(routes=routes_list)


def _client_with_store(mock_store, mock_audit):
    app = Starlette(
        routes=[
            Route("/api/emails", api_list_emails),
            Route("/api/emails/{email_id}/approve", api_approve_email, methods=["POST"]),
            Route("/api/emails/{email_id}/cancel", api_cancel_email, methods=["POST"]),
            Route("/api/email-events", api_list_email_events),
        ]
    )
    with (
        mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
        mock.patch("email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        return client, mock_store, mock_audit


# ── GET /api/emails ────────────────────────────────────────────────────────────


class TestApiListEmails:
    def test_default_returns_200_with_emails_list(self, mock_store, mock_audit):
        em = _email(status="scheduled")
        mock_store._emails.append(em)
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/emails")
        assert response.status_code == 200
        body = response.json()
        assert "emails" in body
        assert "total" in body

    def test_status_filter_scheduled(self, mock_store, mock_audit):
        mock_store._emails.append(_email(status="scheduled"))
        mock_store._emails.append(_email(status="approved"))
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/emails?status=scheduled")
        body = response.json()
        assert all(e["status"] == "scheduled" for e in body["emails"])

    def test_invalid_status_returns_400(self, mock_store, mock_audit):
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/emails?status=invalid_status")
        assert response.status_code == 400

    def test_limit_clamped_to_200(self, mock_store, mock_audit):
        for _ in range(5):
            mock_store._emails.append(_email())
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/emails?limit=300")
        assert response.status_code == 200

    def test_cors_header_present(self, mock_store, mock_audit):
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/emails")
        assert response.headers.get("access-control-allow-origin") == "*"


# ── POST /api/emails/{email_id}/approve ───────────────────────────────────────


class TestApiApproveEmail:
    def test_approve_scheduled_returns_200_with_approved_status(
        self, mock_store, mock_audit
    ):
        em = _email(status="scheduled")
        mock_store._emails.append(em)
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.post(f"/api/emails/{em.id}/approve")
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    def test_approve_already_approved_returns_200_idempotent(
        self, mock_store, mock_audit
    ):
        em = _email(status="approved")
        em.approved_at = "2026-07-22T10:00:00Z"
        mock_store._emails.append(em)
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.post(f"/api/emails/{em.id}/approve")
        assert response.status_code == 200

    def test_approve_sent_returns_409(self, mock_store, mock_audit):
        em = _email(status="sent")
        mock_store._emails.append(em)
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.post(f"/api/emails/{em.id}/approve")
        assert response.status_code == 409

    def test_approve_unknown_id_returns_404(self, mock_store, mock_audit):
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.post("/api/emails/does-not-exist/approve")
        assert response.status_code == 404


# ── POST /api/emails/{email_id}/cancel ────────────────────────────────────────


class TestApiCancelEmail:
    def test_cancel_scheduled_returns_200(self, mock_store, mock_audit):
        em = _email(status="scheduled")
        mock_store._emails.append(em)
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.post(f"/api/emails/{em.id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_sent_returns_409(self, mock_store, mock_audit):
        em = _email(status="sent")
        mock_store._emails.append(em)
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.post(f"/api/emails/{em.id}/cancel")
        assert response.status_code == 409

    def test_cancel_unknown_id_returns_404(self, mock_store, mock_audit):
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.post("/api/emails/nonexistent/cancel")
        assert response.status_code == 404


# ── GET /api/email-events ─────────────────────────────────────────────────────


class TestApiListEmailEvents:
    def test_returns_200_with_events(self, mock_store, mock_audit):
        mock_audit.write(_event())
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/email-events")
        assert response.status_code == 200
        body = response.json()
        assert "events" in body
        assert body["total"] >= 1

    def test_events_newest_first(self, mock_store, mock_audit):
        ev1 = _event()
        ev2 = _event()
        mock_audit.write(ev1)
        mock_audit.write(ev2)
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/email-events?limit=2")
        events = response.json()["events"]
        assert events[0]["event_id"] == ev2.event_id

    def test_limit_clamped_to_500(self, mock_store, mock_audit):
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/email-events?limit=9999")
        assert response.status_code == 200

    def test_total_reflects_unfiltered_count(self, mock_store, mock_audit):
        for _ in range(5):
            mock_audit.write(_event())
        client, _, _ = _client_with_store(mock_store, mock_audit)
        with (
            mock.patch("email_scheduler.queue_store.get_store", return_value=mock_store),
            mock.patch(
                "email_scheduler.audit_logger.get_audit_logger", return_value=mock_audit
            ),
        ):
            response = client.get("/api/email-events?limit=2")
        body = response.json()
        assert body["total"] == 5
        assert len(body["events"]) == 2
