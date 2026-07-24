# ADR-0007: Zero-Build Single-File Dashboard Strategy

- **Status:** Accepted
- **Date:** 2026-07-24
- **Feature:** 006-web-dashboard

**Context:** OpenClaw Deal Scout operates under a strict zero-cost constraint (Constitution Principle I). The project has no CI/CD pipeline beyond `pytest`, no Node.js toolchain, and no deployment infrastructure beyond a single systemd unit on Ubuntu 22.04 WSL2. The feature requires a web UI for the pipeline dashboard.

The central question is: what is the appropriate frontend stack for a single-operator, localhost-only, operator-facing dashboard that must never introduce a paid dependency or build step?

Three dimensions of the decision interact and should be evaluated together:
1. **Technology choice**: which JS/CSS framework or library, if any
2. **File structure**: single file vs multi-file project
3. **Build process**: compiled/bundled vs served raw

These dimensions are tightly coupled: a framework choice (React) implies a build process (Vite/webpack) and a multi-file project structure. Choosing "no framework" collapses all three into a single constraint: one raw HTML file, no build.

**Significance checklist:**
1. Impact: Yes — determines the entire frontend authoring model; affects how future UI features are developed, what tooling contributors need, and whether CI changes are required
2. Alternatives: Yes — React+Vite, Alpine.js, htmx, and Svelte each represent distinct tradeoffs
3. Scope: Yes — cross-cutting; affects `pyproject.toml` (package-data), `server.py` (how the file is served), `routes/api.py` (what the file fetches), CI (what doesn't need to change), and any future frontend contribution

## Decision

The entire dashboard UI is implemented as a single file — `src/openclaw_gateway/static/dashboard.html` — containing inline HTML structure, inline CSS (with CSS custom properties for light/dark theming), and inline JavaScript (ES6, plain `<script>` block).

**Cluster components:**

- **Technology**: Vanilla HTML5 + CSS3 + ES6 JavaScript — no library, no framework, no runtime dependency
- **File structure**: Single file at `src/openclaw_gateway/static/dashboard.html`; zero additional static assets
- **Build process**: None — the file is served directly from disk via `importlib.resources`; no compilation, no bundling, no transpilation, no minification
- **Package integration**: File declared as Python package data in `pyproject.toml` under `[tool.setuptools.package-data]`; resolved at runtime via `importlib.resources.files("openclaw_gateway").joinpath("static/dashboard.html")`
- **Browser compatibility target**: Modern desktop browsers (Chrome 90+, Firefox 88+, Safari 14+) — no polyfills needed; IE/Edge Legacy explicitly out of scope
- **Theming**: CSS `prefers-color-scheme` media query for automatic light/dark mode; CSS custom properties (`--color-*`) for maintainable theming

## Consequences

### Positive

- **Zero toolchain overhead**: No Node.js, no npm, no `node_modules`, no Vite config, no webpack config; a developer can edit the dashboard with any text editor and immediately see changes by refreshing the browser
- **Zero CI/CD changes**: Existing `pytest`-based CI pipeline requires no modification; no build step to add, no artifact to publish
- **No new Python dependencies**: `importlib.resources` is Python stdlib since 3.9; no pip install required
- **Offline-capable by design**: Dashboard loads from a file served locally; no CDN availability dependency (FR-022, SC-007)
- **Editable by non-frontend engineers**: The file is readable HTML/CSS/JS — any engineer familiar with the web platform can contribute without framework knowledge
- **Fast startup**: No module graph to resolve, no hydration phase; browser parses and renders one file
- **Constrained footprint**: The single-file constraint prevents dashboard scope creep — new panels require deliberate effort rather than easily adding new component files

### Negative

- **Authoring ergonomics degrade at scale**: Inline CSS and JS in a single file become harder to maintain as the file grows beyond ~800 lines; no component model, no hot module replacement, no TypeScript type checking
- **No reactive state management**: State updates require manual DOM manipulation (`document.querySelector`, `.textContent = ...`); compared to React/Vue, this is verbose for complex UI interactions
- **No tree-shaking / dead-code elimination**: Any utility function written in the `<script>` block is always sent to the browser, even if unused — not a concern at this scale but relevant if the dashboard grows significantly
- **Testing gap**: No unit tests for JS logic; browser behaviour is verified manually. DOM-manipulation code cannot be tested with pytest; would require a headless browser test runner (Playwright, Puppeteer) to automate
- **Escape hatch requires migration**: If the dashboard complexity grows beyond what vanilla JS handles gracefully (e.g., complex client-side routing, multiple data-dependent panels with loading skeletons), migrating to a framework requires extracting the file into a separate project with its own build process — a non-trivial refactor

## Alternatives Considered

### Alternative A: React + Vite (single-page app, separate build)

Full React component model, JSX, TypeScript, Vite dev server, npm build pipeline. Output is a compiled `dist/` directory served by the gateway as static files.

- **Why rejected**: Introduces Node.js and npm as required development dependencies (not installed in the target environment); adds a build step to CI; the toolchain complexity is a cost in setup and maintenance time. Over-engineered for a single-operator localhost tool with four data panels.

### Alternative B: Alpine.js served from CDN

Thin reactive JS library (~15 KB), usable inline in HTML via `x-data` directives. Eliminates the need for most manual DOM manipulation.

- **Why rejected**: Requires loading Alpine.js from a CDN at runtime, violating FR-022 (no external resources) and SC-007 (must work without internet). Could be self-hosted (vendor the minified file into `static/`), but this adds a vendored third-party file that needs version-tracking and security monitoring — unjustified maintenance overhead for a localhost tool.

### Alternative C: htmx (server-driven UI)

HTML attributes drive HTTP requests; server returns HTML fragments. Eliminates JS data-binding entirely; server renders the UI state.

- **Why rejected**: Requires the gateway to render HTML fragments server-side, not JSON. This would require either a templating engine (Jinja2 — new dependency) or manual string formatting of HTML in Python (unsafe, unmaintainable). The existing REST/JSON contract (ADR-0006) is cleaner and already designed. Same CDN-vs-vendor tradeoff as Alpine.js applies.

### Alternative D: Svelte (compiled to vanilla JS, zero runtime)

Svelte compiles components to minimal vanilla JS with no framework runtime overhead. Output is a small bundle with no React/Vue runtime.

- **Why rejected**: Still requires Node.js + npm + a build step. The "no runtime" advantage doesn't eliminate the build toolchain requirement. The compiled output also produces multiple files (HTML + JS bundle + CSS bundle), complicating the `importlib.resources` single-file serving approach.

### Alternative E: Multi-file vanilla JS (split HTML/CSS/JS)

Same technology as the chosen approach but split into `dashboard.html`, `dashboard.css`, and `dashboard.js` as separate static files.

- **Why not chosen**: Requires the gateway to serve multiple static assets, each needing a custom route or a `StaticFiles` mount. More serving complexity for negligible authoring benefit at this scale. The single-file constraint is a useful forcing function that keeps the dashboard scope bounded.

## References

- Feature Spec: `specs/006-web-dashboard/spec.md` (FR-022: no external resources; SC-007: offline capable)
- Implementation Plan: `specs/006-web-dashboard/plan.md` (Key Design Decision 3)
- Research (Decision 3): `specs/006-web-dashboard/research.md`
- Constitution: `.specify/memory/constitution.md` (Principle I: zero-cost constraint)
- Related ADRs: ADR-0006 (browser-to-gateway REST adapter — defines what the JS fetches), ADR-0004 (gateway HTTP transport — defines what serves the file)
- Evaluator Evidence: `history/prompts/006-web-dashboard/0002-web-dashboard-plan-complete.plan.prompt.md`
