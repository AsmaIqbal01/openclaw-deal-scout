# ADR-0001: Python FastMCP Subprocess Runtime

- **Status:** Accepted
- **Date:** 2026-07-09
- **Feature:** gmail-intake (001-gmail-intake)
- **Context:** The Gmail Intake & Deal Detection module must be exposed as an MCP tool
  (`check_new_deals`) callable by the OpenClaw agent — a Node.js process. A language,
  MCP framework, and process-communication model must be chosen. The decision affects
  every future pipeline tool (HubSpot logging, Discord notification) since they will
  follow the same pattern. The constraints from the constitution are: zero cost,
  headless operation, and graceful degradation — no constraint on implementation language.

## Decision

Implement the Gmail Intake MCP server as a **Python 3.11+ FastMCP subprocess** connected
to OpenClaw via **stdio MCP transport**:

- **Language**: Python 3.11+
- **MCP framework**: `fastmcp ≥2.0` (Python-native; `@mcp.tool()` decorator pattern)
- **Process model**: OpenClaw (Node.js) spawns the Python server as a child subprocess
- **Transport**: stdio (OpenClaw reads/writes JSON-RPC over the subprocess's stdin/stdout)
- **Lifecycle**: Python server process starts when OpenClaw starts, exits when OpenClaw exits

OpenClaw configuration:
```json
{
  "mcpServers": {
    "gmail-intake": {
      "command": "python",
      "args": ["-m", "gmail_intake.server"],
      "cwd": "/path/to/openclaw-deal-scout"
    }
  }
}
```

## Consequences

### Positive

- **Best-in-class SDK support**: Google's Python SDKs (`google-api-python-client`,
  `google-generativeai`) are the most mature for Gmail API and Gemini. The
  `response_mime_type="application/json"` + `response_schema` structured-output
  feature that eliminates manual JSON parsing is stable only in the Python SDK as of 2026-Q2.
- **FastMCP is Python-native**: FastMCP's canonical documentation, examples, and
  tooling are all Python-first; using it in Python means fewer workarounds and a
  well-trodden path.
- **Zero network config**: stdio transport requires no port allocation, no firewall
  rules, and no additional service management — the subprocess is bound to OpenClaw's
  lifecycle automatically.
- **Language isolation**: The Python tool can import any Python library without
  polluting OpenClaw's Node.js `node_modules` dependency graph.
- **Independently testable**: The Python server is a standalone package with its own
  `pytest` test suite, fully testable without running OpenClaw.
- **Portable to other MCP hosts**: Any MCP-compatible agent (not just OpenClaw) can
  invoke `check_new_deals` via stdio — no OpenClaw-specific coupling in the tool code.

### Negative

- **Cross-language complexity**: The operator's machine must have both Node.js (for
  OpenClaw) and Python 3.11+ (for the tool server) installed and in PATH.
- **Subprocess startup latency**: Each time OpenClaw starts, it spawns the Python
  process. Cold-start overhead is ~200–500 ms (Python interpreter startup + module
  imports). Acceptable for a polling tool invoked every few minutes; would be
  unacceptable for sub-second latency requirements.
- **Two dependency manifests**: Node.js `package.json` (OpenClaw) and Python
  `pyproject.toml` (this package) must be maintained separately. Version drift is
  possible.
- **No shared in-process state**: The Python tool cannot share memory or in-process
  state with OpenClaw. All context must be passed via MCP protocol messages or
  environment variables.
- **Debugging cross-process**: Debugging a tool invocation requires tracing across
  the Node.js ↔ stdio ↔ Python boundary. Logs from both processes must be consulted.

## Alternatives Considered

### Alternative A — TypeScript MCP server (same Node.js ecosystem as OpenClaw)

- **Framework**: `@modelcontextprotocol/sdk` (TypeScript)
- **Language**: TypeScript/Node.js
- **Pros**: Single runtime (Node.js only on operator machine); shared `node_modules`;
  same language as OpenClaw; no subprocess overhead.
- **Rejected because**: The official `@google/generative-ai` JS SDK does not support
  `response_schema` structured-output enforcement at the API level as of 2026-Q2,
  requiring brittle manual JSON parsing and a more complex FR-009 (schema validation
  failure) implementation. The Gmail API Node.js client (`googleapis`) is less ergonomic
  than the Python equivalent for the offline OAuth flow. The FastMCP `@mcp.tool()`
  pattern is not available in TypeScript — the TypeScript SDK requires more boilerplate.

### Alternative B — Python tool embedded via child_process (outside MCP protocol)

- **Model**: Node.js calls Python scripts via `child_process.spawn()` outside of MCP protocol
- **Pros**: No MCP overhead; simple function-call semantics from Node.js perspective.
- **Rejected because**: Bypasses the MCP protocol entirely, losing: tool discoverability,
  schema validation, standardised error handling, and the ability to use the tool with any
  other MCP-compatible agent. Violates the modular architecture: pipeline steps should
  be MCP tools, not Node.js helper scripts.

### Alternative C — HTTP/SSE MCP transport (Python server as a persistent daemon)

- **Model**: Python FastMCP server listens on a local HTTP port; OpenClaw connects via SSE
- **Pros**: Server stays warm across multiple OpenClaw restarts; eliminates subprocess startup latency.
- **Rejected because**: Requires port management (allocation, conflict avoidance), a separate
  systemd unit for the Python daemon, and additional networking config on the operator's machine.
  This complexity is not justified for a tool invoked every few minutes. The operator's
  systemd setup should manage OpenClaw; OpenClaw should manage its tool subprocesses.

## References

- Feature Spec: `specs/001-gmail-intake/spec.md`
- Implementation Plan: `specs/001-gmail-intake/plan.md`
- Research (Decision 1 — Language, Decision 2 — Transport): `specs/001-gmail-intake/research.md`
- Related ADRs: ADR-0002 (JSON State Store Mechanism)
- Evaluator Evidence: `history/prompts/gmail-intake/003-gmail-intake-implementation-plan.plan.prompt.md`
