# Specification Quality Checklist: Email Scheduling & Smart Send-Time Optimization

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-07-25
**Revised**: 2026-07-25 (v2 — post spec-scorer REVISE verdict)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes — v2 changes (addressing spec-scorer REVISE verdict 6.1/10)

**Criterion 5 — Interface precision (was 5/10)**
- Added "Interface Contracts" section with full `email_queue.json` field table + example record
- Defined `EmailEvent` with all fields and types
- Added four REST endpoint contracts with request/response shapes, status codes, and idempotency rule
- Added orchestrator integration contract (004→007): `schedule_for_deal(deal_payload)` signature, input fields, return shape, no-raise guarantee
- Replaced all "deal reference" prose with `gmail_message_id: string` throughout

**Criterion 6 — Error path coverage (was 5/10)**
- FR-010: Added exponential back-off intervals (60s / 120s / 240s)
- FR-010: Added escalation after 3 retries: `failed` audit event + `pipeline.log` warning
- Gmail 500/day send cap: added to Constraints; SMTP rate-limit errors treated as retriable failures
- `email_queue.json` partial write failure: FR-013 specifies atomic write (temp + rename); Edge Cases documents `recovered` audit event on startup
- REST state mutation on failed response: Idempotency rule in Interface Contracts; dashboard retries on non-200

**Criterion 4 — Completeness (was 6/10)**
- Gmail 500/day cap: added to Constraints section
- Template fallback: FR-009 now specifies exact fallbacks for missing `sender_name`, `company_name`, `deal_summary`
- Partial write failure handling: FR-013 (atomic write) + Edge Cases (`recovered` event on restart)

**Criterion 7 — Ambiguity (was 6/10)**
- `proposed_send_at`: Assumptions clarifies it is set at scheduling time (advisory); actual dispatch computed from `approved_at` at approval time
- Operator identity: US4 and audit trail now specify `actor: "operator"` (fixed string, not a logged-in identity) and `actor: "system"` for automated events
- "Send immediately" vs 15-min cycle: US3 updated to say "at the next scheduler tick (within 15 minutes)"; Assumptions clarifies dispatch latency is ≤15 minutes

**Criterion 3 — Constitution alignment (was 7/10)**
- Gate 6: FR-017 added — unhandled exceptions in email scheduler MUST NOT propagate to terminate the gateway process
- OAuth re-auth: Assumptions section now explicitly labels it as "setup, not runtime" and states the system is fully headless after initial token refresh

**Criterion 2 — Testability (was 7/10)**
- FR-010 retry interval: 60s / 120s / 240s now specified (testable)
- FR-009 template fallback: exact fallback strings specified per missing field
- DST boundary: US3-S5 added — email approved at 08:15 UTC during BST (= 09:15 BST) correctly dispatched

**Criterion 1 — Scope clarity (was 7/10)**
- "Component Ownership" table added at top of spec: maps 007 (new package), 004 (modified runner), 005/006 (modified gateway) with change types; explicitly states 001, 002, 003 are unchanged
