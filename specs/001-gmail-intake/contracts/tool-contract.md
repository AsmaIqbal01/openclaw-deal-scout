# Tool Contract: check_new_deals

**Branch**: `001-gmail-intake` | **Date**: 2026-07-09
**MCP Server**: `gmail-intake` | **Transport**: stdio

---

## Overview

`check_new_deals` is a zero-parameter MCP tool exposed by the `gmail-intake` Python
FastMCP server. OpenClaw's Gemini-powered agent invokes it on demand to poll the
operator's Gmail inbox, classify new emails, and return structured deal records.

No arguments are passed by the caller. All runtime context (credentials, state store
path, message cap) is provided via environment variables at server startup.

---

## Tool Signature

```
Tool name:   check_new_deals
Parameters:  none
Returns:     CheckNewDealsResult (see below)
```

---

## Environment Variables

Consumed at invocation time (not at import time):

| Variable | Required | Default | Absent behaviour |
|---|---|---|---|
| `GMAIL_CREDENTIALS_PATH` | Yes | — | Fatal startup error: log ERROR, return `status: "error"`, `error_details: "GMAIL_CREDENTIALS_PATH is not set"` |
| `GEMINI_API_KEY` | Yes | — | Fatal startup error: log ERROR, return `status: "error"`, `error_details: "GEMINI_API_KEY is not set"` |
| `STATE_STORE_PATH` | No | `./data/processed_ids.json` | Use default path |
| `MAX_MESSAGES_PER_POLL` | No | `50` | Use default limit |

---

## Return Type: `CheckNewDealsResult`

```python
from typing import TypedDict, Optional

class CheckNewDealsResult(TypedDict):
    status:          str              # "ok" | "error"
    deals_extracted: list[dict]       # List of DealPayload dicts; always a list, never null
    processed_count: int              # Emails fetched from Gmail this run (post-pre-filter)
    skipped_count:   int              # Non-deals + per-email errors (post-pre-filter)
    error_details:   Optional[str]    # Human-readable error string; null when status="ok"
```

### JSON wire format (success, 2 deals from 5 emails)

```json
{
  "status": "ok",
  "deals_extracted": [
    {
      "gmail_message_id": "18f3a4b2c1d0e5f6",
      "sender_email": "alice@example.com",
      "sender_name": "Alice Johnson",
      "subject": "Partnership Inquiry — UK logistics",
      "received_at": "2026-07-09T10:15:00Z",
      "deal_summary": "Alice Johnson from FastRoute Ltd is inquiring about a logistics partnership for UK SMB deliveries. She requests a call to discuss volume pricing.",
      "deal_category": "partnership_inquiry",
      "confidence_score": 0.92,
      "raw_email_excerpt": "Hi, I'm Alice from FastRoute Ltd. We're looking for logistics partners serving UK SMBs..."
    }
  ],
  "processed_count": 5,
  "skipped_count": 3,
  "error_details": null
}
```

### JSON wire format (fatal error — credential failure)

```json
{
  "status": "error",
  "deals_extracted": [],
  "processed_count": 0,
  "skipped_count": 0,
  "error_details": "Gmail token refresh failed: Token has been expired or revoked."
}
```

### JSON wire format (partial run — 1 deal before Gmail rate limit)

```json
{
  "status": "error",
  "deals_extracted": [],
  "processed_count": 12,
  "skipped_count": 3,
  "error_details": "Gmail rate limit: quota exhausted mid-poll after 15 messages"
}
```

Note: On `status: "error"`, `deals_extracted` is always `[]` regardless of how many deals were extracted before the failure point. Counts reflect messages processed before the failure.

---

## Count Semantics

| Counter | What it counts | What it excludes |
|---|---|---|
| `processed_count` | Emails fetched from Gmail in this run that passed the already-processed pre-filter | Emails skipped because their ID was already in the state store (pre-filter skips) |
| `skipped_count` | Emails from `processed_count` that produced no DealPayload (not_a_deal, schema_error, rate_limited, body_absent, invalid_metadata, classification_error) | Pre-filter skips; emails that produced a DealPayload |

Identity: `processed_count = len(deals_extracted) + skipped_count`

---

## Status Semantics

| Status | Trigger | Caller interpretation |
|---|---|---|
| `"ok"` | Poll cycle completed normally (even if inbox was empty or all emails were non-deals) | Treat `deals_extracted` as the authoritative deal list for this cycle |
| `"error"` | Cycle-level fatal: credential failure, network failure, state store read failure, concurrent invocation detected | Do not act on `deals_extracted` (always `[]`); inspect `error_details`; retry strategy is caller's decision |

Per-email failures (schema error, rate limit, body absent, invalid metadata, classification error) do NOT set `status: "error"` — they increment `skipped_count` and the run continues.

---

## Idempotency Guarantee

- The same email will never appear in `deals_extracted` twice across multiple invocations.
- Guarantee mechanism: exclusive file lock on `STATE_STORE_PATH` + pre-invocation state read + per-message atomic write.
- If two invocations are attempted simultaneously, the second returns `status: "error"` with `error_details: "concurrent invocation"` immediately without processing any messages.

---

## Error Detail Taxonomy

| Scenario | `error_details` string |
|---|---|
| `GMAIL_CREDENTIALS_PATH` not set | `"GMAIL_CREDENTIALS_PATH is not set"` |
| `GEMINI_API_KEY` not set | `"GEMINI_API_KEY is not set"` |
| Gmail token refresh failed | `"Gmail token refresh failed: <google auth error message>"` |
| State store unreadable | `"State store unreadable: <OS error message>"` |
| Concurrent invocation | `"concurrent invocation"` |
| Gmail rate limit (cycle abort) | `"Gmail rate limit: <details if available>"` |
| Network failure mid-poll | `"Network failure mid-poll: <error message>"` |

`error_details` contains the top-level error message only. No stack traces. Full stack traces are written to the error log (FR-020).

---

## MCP Tool Definition (FastMCP Python)

```python
from fastmcp import FastMCP
from gmail_intake.server import check_new_deals_handler

mcp = FastMCP("gmail-intake")

@mcp.tool()
async def check_new_deals() -> dict:
    """
    Poll the operator's Gmail inbox for new business deal emails.
    Returns structured DealPayload records for confirmed deals.
    No parameters required — all config is via environment variables.
    """
    return await check_new_deals_handler()
```

---

## Versioning

This contract is v1.0. Any change to parameter set, return shape, field types, or
status semantics constitutes a breaking change and requires a new spec revision.
Non-breaking additions (new optional fields in DealPayload, new `error_details`
strings) are minor changes — document in the plan amendment, not a new spec.
