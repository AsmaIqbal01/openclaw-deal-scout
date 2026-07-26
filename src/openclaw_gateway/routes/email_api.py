"""REST handlers for email scheduling endpoints (/api/emails/* and /api/email-events)."""
from __future__ import annotations

import asyncio
import dataclasses

from starlette.requests import Request
from starlette.responses import JSONResponse

_VALID_EMAIL_STATUSES = frozenset(
    {"all", "scheduled", "approved", "sent", "cancelled", "failed"}
)


def _json_response(data: dict, status: int = 200) -> JSONResponse:
    resp = JSONResponse(data, status_code=status)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# ── GET /api/emails ───────────────────────────────────────────────────────────


async def api_list_emails(request: Request) -> JSONResponse:
    status_param = request.query_params.get("status", "all")
    if status_param not in _VALID_EMAIL_STATUSES:
        return _json_response(
            {
                "error": "invalid_status",
                "valid_values": sorted(_VALID_EMAIL_STATUSES),
            },
            status=400,
        )

    try:
        raw_limit = request.query_params.get("limit", "50")
        try:
            limit = max(1, min(200, int(raw_limit)))
        except ValueError:
            limit = 50

        raw_offset = request.query_params.get("offset", "0")
        try:
            offset = max(0, int(raw_offset))
        except ValueError:
            offset = 0

        from email_scheduler.queue_store import get_store

        store = get_store()
        filter_arg = None if status_param == "all" else status_param
        emails = store.list_emails(status_filter=filter_arg)

        # Sort newest first
        emails.sort(key=lambda e: e.created_at, reverse=True)
        total = len(emails)
        page = emails[offset: offset + limit]

        return _json_response(
            {
                "emails": [dataclasses.asdict(e) for e in page],
                "total": total,
                "offset": offset,
            }
        )
    except Exception as exc:
        return _json_response({"error": "queue_read_failed", "detail": str(exc)}, status=500)


# ── POST /api/emails/{email_id}/approve ───────────────────────────────────────


async def api_approve_email(request: Request) -> JSONResponse:
    email_id = request.path_params.get("email_id", "")
    try:
        from email_scheduler.audit_logger import get_audit_logger
        from email_scheduler.models import EmailEvent, EventType
        from email_scheduler.queue_store import get_store, _utcnow_iso
        import uuid

        store = get_store()
        audit = get_audit_logger()

        try:
            email = await asyncio.to_thread(store.approve, email_id)
        except KeyError:
            return _json_response({"error": "not_found", "email_id": email_id}, status=404)
        except ValueError as exc:
            return _json_response(
                {
                    "error": "invalid_transition",
                    "email_id": email_id,
                    "current_status": str(exc),
                    "requested": "approve",
                },
                status=409,
            )
        except OSError as exc:
            return _json_response(
                {"error": "state_write_failed", "detail": str(exc)}, status=500
            )

        # Write audit event (best-effort — failure is logged but does not block response)
        try:
            audit.write(EmailEvent(
                event_id=str(uuid.uuid4()),
                email_id=email.id,
                gmail_message_id=email.gmail_message_id,
                event_type=EventType.APPROVED.value,
                timestamp=_utcnow_iso(),
                actor="operator",
                recipient_email=email.recipient_email,
            ))
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "[WARN] audit_write_failed for approve on email %s", email_id
            )

        return _json_response(
            {
                "id": email.id,
                "status": email.status,
                "approved_at": email.approved_at,
            }
        )

    except Exception as exc:
        return _json_response({"error": "state_write_failed", "detail": str(exc)}, status=500)


# ── POST /api/emails/{email_id}/cancel ────────────────────────────────────────


async def api_cancel_email(request: Request) -> JSONResponse:
    email_id = request.path_params.get("email_id", "")
    try:
        from email_scheduler.audit_logger import get_audit_logger
        from email_scheduler.models import EmailEvent, EventType
        from email_scheduler.queue_store import get_store, _utcnow_iso
        import uuid

        store = get_store()
        audit = get_audit_logger()

        try:
            email = await asyncio.to_thread(store.cancel, email_id)
        except KeyError:
            return _json_response({"error": "not_found", "email_id": email_id}, status=404)
        except ValueError as exc:
            return _json_response(
                {
                    "error": "invalid_transition",
                    "email_id": email_id,
                    "current_status": str(exc),
                    "requested": "cancel",
                },
                status=409,
            )
        except OSError as exc:
            return _json_response(
                {"error": "state_write_failed", "detail": str(exc)}, status=500
            )

        try:
            audit.write(EmailEvent(
                event_id=str(uuid.uuid4()),
                email_id=email.id,
                gmail_message_id=email.gmail_message_id,
                event_type=EventType.CANCELLED.value,
                timestamp=_utcnow_iso(),
                actor="operator",
                recipient_email=email.recipient_email,
            ))
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "[WARN] audit_write_failed for cancel on email %s", email_id
            )

        return _json_response(
            {
                "id": email.id,
                "status": email.status,
                "cancelled_at": email.cancelled_at,
            }
        )

    except Exception as exc:
        return _json_response({"error": "state_write_failed", "detail": str(exc)}, status=500)


# ── GET /api/email-events ─────────────────────────────────────────────────────


async def api_list_email_events(request: Request) -> JSONResponse:
    try:
        raw_limit = request.query_params.get("limit", "100")
        try:
            limit = max(1, min(500, int(raw_limit)))
        except ValueError:
            limit = 100

        raw_offset = request.query_params.get("offset", "0")
        try:
            offset = max(0, int(raw_offset))
        except ValueError:
            offset = 0

        import dataclasses as _dc
        from email_scheduler.audit_logger import get_audit_logger

        audit = get_audit_logger()
        all_events = audit.get_events()  # newest first
        total = len(all_events)
        page = all_events[offset: offset + limit]

        return _json_response(
            {
                "events": [_dc.asdict(e) for e in page],
                "total": total,
                "offset": offset,
            }
        )
    except Exception as exc:
        return _json_response({"error": "audit_read_failed", "detail": str(exc)}, status=500)
