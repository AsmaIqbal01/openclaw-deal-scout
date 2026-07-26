"""Data models for the email_scheduler package."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EmailStatus(str, Enum):
    SCHEDULED = "scheduled"
    APPROVED = "approved"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EventType(str, Enum):
    SCHEDULED = "scheduled"
    APPROVED = "approved"
    CANCELLED = "cancelled"
    SENT = "sent"
    FAILED = "failed"
    NO_RECIPIENT = "no-recipient"
    DUPLICATE = "duplicate-skipped"
    SCHEDULER_ERROR = "scheduler-error"
    RECOVERED = "recovered"
    RECOVERY_WARN = "recovery-warning"


class AuthError(Exception):
    """Gmail send token refresh or credential load failed."""


@dataclass
class ScheduledEmail:
    id: str
    gmail_message_id: str
    recipient_name: str | None
    recipient_email: str
    subject: str
    body: str
    status: str  # EmailStatus enum value
    proposed_send_at: str
    created_at: str
    approved_at: str | None = None
    sent_at: str | None = None
    cancelled_at: str | None = None
    failed_at: str | None = None
    retry_count: int = 0
    retry_after: str | None = None
    last_error: str | None = None


@dataclass
class EmailEvent:
    event_id: str
    email_id: str | None
    gmail_message_id: str | None
    event_type: str  # EventType enum value
    timestamp: str
    actor: str  # "operator" or "system"
    recipient_email: str | None = None
    error_detail: str | None = None
    retry_count: int | None = None
