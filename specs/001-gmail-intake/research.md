# Phase 0 Research: Gmail Intake & Deal Detection

**Branch**: `001-gmail-intake` | **Date**: 2026-07-09
**Resolves**: All NEEDS CLARIFICATION items from `plan.md` Technical Context

---

## Decision 1 — Implementation Language

**Decision**: Python 3.11+

**Rationale**:
- `fastmcp` is a Python library; Python is its native runtime
- Google provides first-class Python SDKs for Gmail API (`google-api-python-client`) and Gemini (`google-generativeai`)
- `google-generativeai` Python SDK supports `response_mime_type="application/json"` and `response_schema` for Gemini structured output — the feature that eliminates manual JSON parsing and makes FR-009 (schema validation failure handling) clean
- Gemini structured-output (controlled generation) is best-documented and most stable in the Python SDK as of 2026-Q2

**Alternatives considered**:
- TypeScript (Node.js): OpenClaw runs in Node, so a TS MCP server could share the process. Rejected because the official `@google/generative-ai` JS SDK has weaker structured-output support; FastMCP's canonical tooling is Python.
- Same Node.js process as OpenClaw: eliminates the subprocess hop but requires OpenClaw customisation that violates the modular architecture principle.

---

## Decision 2 — MCP Transport

**Decision**: stdio transport (OpenClaw spawns the Python server as a child process)

**Rationale**:
- stdio is the simplest MCP transport: no ports, no network config, no firewall rules
- OpenClaw's MCP configuration supports stdio-spawned servers natively
- On the operator's Linux machine (single user, WSL), there is no multi-process isolation benefit to using SSE/HTTP transport that would justify the added complexity

**Alternatives considered**:
- HTTP/SSE transport: would allow the Python server to run as a persistent daemon. Rejected for MVP — the operator's systemd setup manages OpenClaw, which manages the Python subprocess lifetime.
- Embedded Python (subprocess via Node child_process): non-standard, loses MCP protocol benefits.

**OpenClaw MCP config snippet** (for `~/.openclawrc.json` or equivalent):
```json
{
  "mcpServers": {
    "gmail-intake": {
      "command": "python",
      "args": ["-m", "gmail_intake.server"],
      "cwd": "/path/to/openclaw-deal-scout",
      "env": {
        "GMAIL_CREDENTIALS_PATH": "${GMAIL_CREDENTIALS_PATH}",
        "STATE_STORE_PATH": "${STATE_STORE_PATH}",
        "MAX_MESSAGES_PER_POLL": "${MAX_MESSAGES_PER_POLL}",
        "GEMINI_API_KEY": "${GEMINI_API_KEY}"
      }
    }
  }
}
```

---

## Decision 3 — Gmail API Auth Flow

**Decision**: OAuth 2.0 offline flow with stored token file; programmatic refresh via `google.auth.transport.requests.Request()`

**Credential files** (both gitignored, never committed):
- `credentials.json` — OAuth client credentials (client_id, client_secret) from Google Cloud Console; path set by `GMAIL_CREDENTIALS_PATH`
- `token.json` — OAuth token file (access_token, refresh_token, expiry); stored in the same directory as `credentials.json`, named `token.json` by convention

**One-time setup** (offline, not a runtime step):
```bash
python -m gmail_intake.setup_oauth
# Opens browser once, user logs in, saves token.json
# Never run again unless token is manually revoked
```

**Runtime refresh** (programmatic, headless):
```python
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

creds = Credentials.from_authorized_user_file(token_path, SCOPES)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())   # one attempt; raises google.auth.exceptions.TransportError on failure
```

**Required OAuth scope**: `https://www.googleapis.com/auth/gmail.readonly`

**Rationale**: Read-only scope is the minimum needed; avoids accidental mutation of the mailbox.

---

## Decision 4 — File Lock for Concurrency (FR-003b)

**Decision**: `portalocker` library with `LOCK_EX | LOCK_NB`

**Implementation**:
```python
import portalocker

def acquire_lock(lock_path: str) -> portalocker.Lock:
    lock = portalocker.Lock(lock_path, mode='a', flags=portalocker.LOCK_EX | portalocker.LOCK_NB)
    try:
        lock.acquire()
        return lock
    except portalocker.exceptions.LockException:
        raise ConcurrentInvocationError("concurrent invocation detected — aborting")
```

**Rationale**: `LOCK_NB` (non-blocking) raises immediately if the lock is held; no timeout needed per spec. `portalocker` wraps `fcntl.flock()` on Linux and `msvcrt.locking()` on Windows, making the code portable if the project ever runs outside WSL. Lock file: `{STATE_STORE_PATH}.lock` (separate from the state store to allow the store to be read while the lock is being released).

**Alternatives considered**:
- `fcntl.flock()` directly: Linux-only, acceptable for this project but portalocker adds no weight.
- PID file: doesn't release atomically on crash; portalocker's OS-managed lock releases on process death.

---

## Decision 5 — Atomic State Store Writes (FR-013)

**Decision**: Write to `{path}.tmp`, then `os.rename()` to `{path}`

**Implementation pattern**:
```python
import os, json, tempfile

def atomic_write(path: str, data: dict) -> None:
    dir_path = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        mode='w', dir=dir_path, suffix='.tmp', delete=False, encoding='utf-8'
    ) as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path = f.name
    os.rename(tmp_path, path)   # POSIX atomic on same filesystem
```

**Rationale**: `os.rename()` on POSIX filesystems is atomic when source and destination are on the same mount. Writing to the same directory as the state store guarantees same-mount placement. A crash between `NamedTemporaryFile` creation and `rename` leaves a `.tmp` file — harmless, cleaned up on next successful write.

---

## Decision 6 — Gemini Structured Output (FR-006, FR-009)

**Decision**: `google-generativeai` with `response_mime_type="application/json"` and `response_schema`

**Implementation**:
```python
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config=GenerationConfig(
        response_mime_type="application/json",
        response_schema={
            "type": "object",
            "properties": {
                "is_deal":          {"type": "boolean"},
                "confidence_score": {"type": "number"},
                "deal_category":    {"type": "string", "nullable": True},
                "deal_summary":     {"type": "string", "nullable": True},
                "raw_email_excerpt":{"type": "string", "nullable": True}
            },
            "required": ["is_deal", "confidence_score", "deal_category", "deal_summary", "raw_email_excerpt"]
        }
    )
)
```

**Rationale**: Gemini enforces the schema at the API level before returning. This means the Python code never receives a malformed JSON blob; it only needs to handle field-level validation (types, ranges), not JSON parse errors. This dramatically simplifies FR-009 (schema validation failure) handling.

---

## Decision 7 — Classifier Prompt (FR-006)

The exact prompt text below is version-controlled here (per FR-006). Any change to this prompt MUST be reflected in a new spec revision or plan amendment.

**Prompt template** (Python f-string; `{...}` are substituted at runtime):

```
You are a business deal classifier for an automated email assistant serving UK micro-businesses (fewer than 10 employees).

Analyse the following email and determine whether it represents a genuine business deal opportunity — such as a sales lead, partnership inquiry, vendor quote request, or RFQ — directed at a UK micro-business.

Email details:
Subject: {subject}
Sender: {sender_name_or_anonymous} <{sender_email}>
Body:
{body_excerpt}

Target segment: {target_segment}

Classification rules:
1. Set is_deal=true ONLY for genuine business opportunities (leads, inquiries, partnership offers, vendor quotes, RFQs).
2. Set is_deal=false for: newsletters, marketing emails, spam, personal emails, automated notifications, transactional emails, and any email not directly relevant to business development.
3. confidence_score must reflect your certainty: 1.0 = certain, 0.5 = borderline, 0.0 = definitely not a deal.
4. If is_deal=false OR confidence_score < 0.5, set deal_category, deal_summary, and raw_email_excerpt to null.
5. deal_summary must be exactly 1–2 sentences describing the opportunity. No more.
6. raw_email_excerpt must be a verbatim short excerpt from the body (max 500 characters, ending at a word boundary) most relevant to the deal. Not a summary — a direct quote.
7. deal_category must be exactly one of: lead, partnership_inquiry, vendor_offer, rfq, other.
8. All five fields are required in your response even when is_deal=false.

Respond with a JSON object only. No prose. No markdown fences.
```

**Prompt versioning**: This is prompt v1.0. If the prompt changes, increment the version and record the change in a plan amendment commit.

---

## Decision 8 — FR-011 Sentence Boundary Regex

**Problem**: FR-011 defines sentence boundaries as `.!?` followed by space or EOS, excluding mid-word abbreviation periods. The spec-scorer (round 11) flagged that title abbreviations (`Dr.`, `Mr.`, `Mrs.`) before a space are also not sentence boundaries — but FR-011's wording doesn't explicitly cover them.

**Resolution** (plan-level clarification of FR-011):

A sentence boundary is a `.`, `!`, or `?` followed by whitespace or EOS, **unless** the `.` is immediately preceded by any of the following exclusion patterns:

1. **Known title abbreviations**: `Mr`, `Mrs`, `Ms`, `Dr`, `Prof`, `Sr`, `Jr`, `St`, `Ltd`, `vs`, `etc`, `eg`, `ie`, `approx`, `dept`, `Fig`, `No`
2. **Mid-word acronyms**: any sequence matching `[A-Z](\.[A-Z])+` (e.g., `U.K.`, `U.S.A.`)
3. **Single uppercase letter** (initials): `\b[A-Z]\.` followed by space + uppercase

**Exact regex implementation**:

```python
import re

# Patterns that produce a period which is NOT a sentence boundary
_TITLE_ABBREVS = r'(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|Ltd|vs|etc|eg|ie|approx|dept|Fig|No)'
_NON_SENTENCE_DOT = re.compile(
    r'(?:' + _TITLE_ABBREVS + r')\.'     # Title abbreviations
    r'|(?:[A-Z]\.){2,}'                    # Acronyms: U.K., U.S.A.
    r'|\b[A-Z]\.'                          # Single initials: J. Smith
)

_SENTENCE_END = re.compile(r'(?<![.!?])[.!?](?=\s|$)')

def split_sentences(text: str) -> list[str]:
    """
    Split text into sentences. Excludes title abbreviations, acronyms, initials.
    Returns a list of sentence strings (with trailing punctuation).
    """
    # Replace non-sentence dots with a placeholder
    protected = _NON_SENTENCE_DOT.sub(lambda m: m.group().replace('.', '\x00'), text)
    # Split on remaining sentence-ending punctuation
    parts = _SENTENCE_END.split(protected)
    # Restore placeholders and strip
    sentences = [p.replace('\x00', '.').strip() for p in parts if p.strip()]
    return sentences

def truncate_summary(text: str, max_sentences: int = 2, max_chars: int = 500) -> str:
    """FR-011: sentence rule first, then 500-char hard cap."""
    sentences = split_sentences(text)
    truncated = ' '.join(sentences[:max_sentences])
    if len(truncated) > max_chars:
        # Word-boundary truncation
        truncated = truncated[:max_chars].rsplit(' ', 1)[0]
    return truncated
```

**Test cases** (to be added to `tests/unit/test_extractor.py`):

| Input | Expected output |
|---|---|
| `"Hello Dr. Smith. This is a deal."` | `"Hello Dr. Smith. This is a deal."` (2 sentences, no split at Dr.) |
| `"We operate in the U.K. Our offer stands."` | `"We operate in the U.K. Our offer stands."` (2 sentences) |
| `"Lead received. Details follow. More info later."` | `"Lead received. Details follow."` (capped at 2 sentences) |
| `"A very long sentence..."` (>500 chars) | Truncated at word boundary ≤500 chars |
| `"Mr. Jones confirmed. Ms. Lee agreed. Next steps follow."` | `"Mr. Jones confirmed. Ms. Lee agreed."` (2 sentences) |

---

## Decision 9 — State Store Size Warning

**Decision**: Check `os.path.getsize(STATE_STORE_PATH)` once per cycle after the lock is acquired; log WARN if >50 MB.

**Implementation**:
```python
STATE_STORE_WARN_BYTES = 50 * 1024 * 1024  # 50 MB

def check_store_size(path: str) -> None:
    try:
        size = os.path.getsize(path)
        if size > STATE_STORE_WARN_BYTES:
            logger.warning(
                "state store exceeding 50 MB (%.1f MB) — archival recommended",
                size / (1024 * 1024)
            )
    except OSError:
        pass  # File doesn't exist yet on first run — not an error
```

---

## Decision 10 — Environment Variable Handling

All env vars are read at tool invocation time (not at module import time) so the server can start before `.env` is populated in test environments.

```python
import os

def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Required env var {name} is not set")
    return value

def get_optional_env(name: str, default: str) -> str:
    return os.environ.get(name) or default
```

Usage in `server.py`:
```python
GMAIL_CREDENTIALS_PATH = get_required_env("GMAIL_CREDENTIALS_PATH")  # fatal if absent
STATE_STORE_PATH        = get_optional_env("STATE_STORE_PATH", "./data/processed_ids.json")
MAX_MESSAGES_PER_POLL   = int(get_optional_env("MAX_MESSAGES_PER_POLL", "50"))
GEMINI_API_KEY          = get_required_env("GEMINI_API_KEY")
```

Note: `GEMINI_API_KEY` is required but not in the spec's Tool Contract table. Adding it here as it is implicitly required for the classifier module. It should be added to `.env.example`.
