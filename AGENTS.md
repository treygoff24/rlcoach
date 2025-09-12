# Repository Guidelines

## Project Structure & Module Organization
- `codex/Plans/` — single source of truth for scope. Start with `codex/Plans/rlcoach_implementation_plan.md` before proposing changes.
- `codex/docs/` — design notes and workflow guides. Keep docs self‑contained; cross‑link related sections.
- `codex/tickets/` — work items. Create from `TICKET_TEMPLATE.md` (e.g., `codex/tickets/2025-09-08-add-replay-parser.md`).
- `codex/logs/` — engineering logs; date‑prefixed files (e.g., `2025-09-08-session.md`).
- `src/` — future code; tests mirror under `tests/`. JSON schemas in `schemas/`. Large replays in `assets/replays/` (use Git LFS).

## Build, Test, and Development Commands
- `make install-dev` — install dev deps (pytest, ruff, black).
- `make test` — run pytest quickly (`-q`).
- `make fmt` — format code with Black (88 cols).
- `make lint` — static checks via Ruff.
- `make clean` — remove caches and build artifacts.
- Docs helpers: `cp codex/tickets/TICKET_TEMPLATE.md codex/tickets/2025-09-08-short-title.md` and `cp codex/logs/LOG_TEMPLATE.md codex/logs/2025-09-08-yourname.md`.

## Coding Style & Naming Conventions
- Markdown: Title Case headings; kebab‑case filenames (e.g., `gpt5-agentic-workflow-guide.md`).
- JSON: 2‑space indent, snake_case keys, deterministic field order; include minimal examples.
- Python: modules/functions `snake_case`, types `PascalCase`; favor small, pure functions.
- Tooling: Black + Ruff; keep patches minimal and focused.

## Testing Guidelines
- Framework: pytest; name tests `test_*.py` and mirror `src/` paths.
- Targets: ≥80% coverage for analyzers and schema validators.
- Fixtures: keep small; store sample replays in `assets/replays/`.
- Run: `make test` or `pytest -q`. Include one happy path and one degraded/fallback case per feature.

## Commit & Pull Request Guidelines
- Conventional Commits (e.g., `feat(parser): add header-only fallback`).
- One logical change per PR; include rationale and before/after artifacts (e.g., sample JSON).
- Link tickets (e.g., `Relates-to: codex/tickets/2025-09-08-add-replay-parser.md`). Update docs/schemas alongside code.

## Security & Agent Notes
- All‑local analysis; avoid network calls in core analyzers. Do not commit large or sensitive replays; use Git LFS for big assets.
- For Codex CLI agents: read `codex/Plans/rlcoach_implementation_plan.md` first, update plans as you work, prefer targeted tests over broad refactors, and avoid unrelated reformatting.
