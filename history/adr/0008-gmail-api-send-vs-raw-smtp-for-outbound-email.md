# ADR-0008: Gmail API Send vs Raw SMTP for Outbound Email

- **Status:** Accepted
- **Date:** 2026-07-26
- **Feature:** 007-email-scheduling

- **Context:** Feature 007 requires the pipeline to send follow-up emails via the operator's
  existing Gmail account. Two viable mechanisms exist: (1) the Gmail REST API
  (`users().messages().send()`), and (2) raw SMTP using Python's `smtplib` with XOAUTH2
  authentication. Both send from the same Gmail account using the same OAuth2 credentials
  stored in `token.json`. The choice determines how authentication is handled at send time,
  what new dependencies (if any) are introduced, how errors are surfaced, and what OAuth
  scope the operator must authorise. The decision is cross-cutting: it affects
  `email_scheduler.auth`, `email_scheduler.scheduler` (dispatch path), the one-time setup
  instructions, and every SMTP error-handling path in FR-010.

## Decision

Use the **Gmail REST API** (`googleapiclient.discovery.build('gmail', 'v1', credentials=creds)`
→ `service.users().messages().send(userId='me', body={'raw': raw_b64})`) as the outbound
email transport for 007.

- **Auth module**: `email_scheduler.auth.build_send_service(credentials_path)` — mirrors
  `gmail_intake.gmail_client.build_service()` but with scope
  `https://www.googleapis.com/auth/gmail.send` (least-privilege send scope, not full
  `https://mail.google.com/`).
- **Message construction**: Python stdlib `email.mime.text.MIMEText` → `base64.urlsafe_b64encode(msg.as_bytes()).decode()` → `{'raw': encoded}` — no new dependencies.
- **Token refresh**: Handled natively by `google.oauth2.credentials.Credentials.refresh()`,
  identical to the existing `gmail_intake` pattern.
- **One-time setup**: Operator re-runs the OAuth consent flow to add `gmail.send` scope to
  the existing `token.json`. After that, both `gmail_intake` (readonly) and `email_scheduler`
  (send) work from the same `token.json` without further browser interaction.
- **001-gmail-intake unchanged**: No shared auth module extraction in v1. `email_scheduler.auth`
  duplicates ~20 lines of credential-loading code. This preserves the spec constraint that
  001 remains unmodified.

## Consequences

### Positive

- **Zero new dependencies**: `google-api-python-client` is already in the venv via `gmail_intake`.
  Adding the Gmail API send path requires only a new scope constant and a new function in
  `email_scheduler.auth` — no `pip install`.
- **Native OAuth2 token refresh**: The `google.oauth2.credentials.Credentials` object handles
  token expiry and refresh automatically; no manual XOAUTH2 base64 string or SASL handshake
  required.
- **Consistent error taxonomy**: Gmail API `HttpError` (with HTTP status codes 400/403/429/5xx)
  maps directly to the retry policy in FR-010. `403` = auth/scope failure; `429` = rate limit;
  `5xx` = transient. Contrast with raw SMTP where errors arrive as SMTP reply codes (535 auth
  failure, 421 temporarily unavailable) requiring a separate error taxonomy.
- **Least-privilege scope**: `gmail.send` allows sending but not reading inbox — more restrictive
  than `https://mail.google.com/` (full IMAP/SMTP access). Reduces the risk surface if
  `token.json` is ever compromised.
- **Proven pattern**: `gmail_intake` already uses this library and credential approach;
  no new integration surface for the operator to manage.

### Negative

- **`google-api-python-client` version coupling**: If `gmail_intake` upgrades the library,
  `email_scheduler` inherits the upgrade silently. In the opposite case (if auth API changes),
  both modules are affected. Acceptable risk: both modules are in the same repo and venv.
- **Credential code duplication**: `email_scheduler.auth.build_send_service()` duplicates
  ~20 lines from `gmail_intake.gmail_client.build_service()`. If the credential-loading
  pattern changes (e.g., a new Google Auth library version), both files must be updated.
  A future refactor (extract `gmail_intake.auth.load_credentials()`) would eliminate this
  duplication but is explicitly deferred to a future spec to avoid changing 001 in this
  feature.
- **Scope re-auth required**: The operator must perform a one-time OAuth consent flow to add
  `gmail.send` to their existing `token.json`. Until this is done, all `dispatch_pending()`
  calls fail with `HttpError 403`. The failure is caught, logged, and marked as a
  `scheduler-error` audit event — the gateway continues running, but no emails are sent.
- **Gmail API rate limits**: The Gmail API enforces per-user quotas (250 quota units per
  `messages.send` call; 1 billion quota units per day). At <20 emails/day this is negligible.
  If usage grows, a migration to a dedicated transactional email provider would be needed —
  at which point a new ADR would supersede this one.

## Alternatives Considered

### Alternative A — Raw SMTP via smtplib + XOAUTH2 (port 587, STARTTLS)

Python's `smtplib.SMTP('smtp.gmail.com', 587)` with `smtp.starttls()` and manual XOAUTH2
authentication string:

```python
auth_string = base64.b64encode(
    f"user={from_email}\x01auth=Bearer {access_token}\x01\x01".encode()
).decode()
smtp.docmd('AUTH', 'XOAUTH2 ' + auth_string)
```

**Why rejected**: (1) `smtplib` has no native OAuth2 token-refresh support — the caller must
refresh the token manually before constructing the auth string, adding ~15 lines of custom
refresh code. (2) SMTP error codes (535, 421, 550) require a separate mapping to the retry
policy defined in FR-010; the Gmail API's HTTP codes map more cleanly. (3) SMTP connections
use port 587 (or 465 for SSL), which may be blocked by some network environments. (4) The
scope required for raw SMTP is `https://mail.google.com/` (full Gmail access), which is
broader than the `gmail.send` scope sufficient for the API approach.

### Alternative B — Third-party transactional email service (SendGrid, Mailgun, Postmark)

Use a dedicated email delivery API instead of Gmail.

**Why rejected**: Violates Constitution Principle I (zero recurring cost) — all major
transactional email providers require a paid plan once the free tier limit is exceeded
(SendGrid: 100/day free; Mailgun: 5,000/month; Postmark: paid only). The product serves
low-infrastructure operators for whom any external cost is a barrier. Additionally,
setting up DKIM/SPF for a new sending domain adds operational overhead not present with the
operator's existing Gmail account.

### Alternative C — Extract shared auth module from gmail_intake

Refactor `gmail_intake.gmail_client.build_service()` to expose a public
`gmail_intake.auth.load_credentials(token_path, scopes)` helper, then call it from both
`gmail_intake` and `email_scheduler`.

**Why deferred**: Requires a change to 001-gmail-intake, which the spec explicitly constrains
as "unchanged" in the Component Ownership table. Deduplication is ~20 lines of stable code;
the risk of a bad refactor outweighs the benefit in v1. If a third package requires Gmail
auth in the future, this extraction becomes worth doing and a new ADR should capture it.

## References

- Feature Spec: `specs/007-email-scheduling/spec.md` (FR-007, Assumptions — OAuth scope)
- Implementation Plan: `specs/007-email-scheduling/plan.md` (Decision 1, Decision 3)
- Research: `specs/007-email-scheduling/research.md` (R-001, R-006)
- Related ADRs: ADR-0005 (gateway threading model — independent decision)
- PHR: `history/prompts/007-email-scheduling/0002-email-scheduling-plan-007.plan.prompt.md`
