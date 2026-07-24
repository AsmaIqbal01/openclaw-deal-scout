---
id: "0004"
title: ADR Zero-Build Single-File Dashboard
stage: misc
date: 2026-07-24
surface: agent
model: claude-sonnet-4-6
feature: 006-web-dashboard
branch: 006-web-dashboard
user: AsmaIqbal01
command: /sp.adr dashboard-zero-build-single-file
labels: ["adr","architecture","frontend","vanilla-js","zero-build","single-file"]
links:
  spec: specs/006-web-dashboard/spec.md
  ticket: "null"
  adr: history/adr/0007-zero-build-single-file-dashboard-strategy.md
  pr: "null"
files:
  - history/adr/0007-zero-build-single-file-dashboard-strategy.md
tests:
  - "null"
---

## Prompt

/sp.adr dashboard-zero-build-single-file

## Response snapshot

Created ADR-0007: Zero-Build Single-File Dashboard Strategy.

**Decision**: The entire dashboard UI is one file (`src/openclaw_gateway/static/dashboard.html`) with inline HTML, CSS (CSS custom properties for dark/light theme), and ES6 JavaScript. No build process, no Node.js, no npm. File served via `importlib.resources` and declared in `pyproject.toml` package-data. Browser target: Chrome 90+, Firefox 88+, Safari 14+.

**Significance test**: PASS on all three gates — determines entire frontend authoring model (impact), 5 alternatives evaluated (alternatives), affects pyproject.toml/server.py/routes/CI (scope).

**5 alternatives evaluated**: React+Vite (build step, Node.js — rejected), Alpine.js CDN (violates FR-022 — rejected), htmx (requires server-side HTML rendering — rejected), Svelte (still needs build — rejected), multi-file vanilla JS (extra routing complexity — not chosen).

**Existing ADRs checked**: 0001–0006 (including 0006 written this session), none conflict. ADR-0006, ADR-0004 referenced as related.

## Outcome

- ✅ Impact: Both dashboard ADRs now documented; planning phase fully complete; all architectural decisions recorded
- 🧪 Tests: None at ADR stage
- 📁 Files: 1 file written (history/adr/0007-zero-build-single-file-dashboard-strategy.md)
- 🔁 Next prompts: `/sp.tasks` to generate the executable task list and begin implementation
- 🧠 Reflection: The "escape hatch requires migration" negative consequence is the most important one to document — it sets the expectation that the single-file approach is a deliberate bet on this dashboard staying small, not an oversight

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): Significance test PASS (3/3); ADR checklist PASS (5 alternatives, pros/cons, references, no over-granularity)
- Prompt variant (if applicable): "null"
- Next experiment: "null"
