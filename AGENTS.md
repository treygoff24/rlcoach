# Repository Guidelines

## Project Structure & Module Organization
- `codex/Plans/` — single source of truth for scope. Start with `codex/Plans/rlcoach_implementation_plan.md` before proposing changes.
- `codex/docs/` — design notes and workflow guides. Keep documents self‑contained and cross‑link related sections.
- `codex/tickets/` — work items. Create new tickets from `TICKET_TEMPLATE.md`; example: `codex/tickets/2025-09-08-add-replay-parser.md`.
- `codex/logs/` — engineering logs. Prefer date‑prefixed filenames (e.g., `2025-09-08-session.md`).
- Future code lives in `src/` with mirrored tests in `tests/`; JSON schemas in `schemas/`.

## Build, Test, and Development Commands
- Create a ticket: `cp codex/tickets/TICKET_TEMPLATE.md codex/tickets/2025-09-08-short-title.md`.
- Start a log: `cp codex/logs/LOG_TEMPLATE.md codex/logs/2025-09-08-yourname.md`.
- Validate JSON snippets embedded in docs: `jq -e . <<< "$(pbpaste)"` or `jq -e . file.json`.
- This repo has no build pipeline yet. If adding code, include simple `make` targets: `make test`, `make fmt`, and document language‑specific setup in the PR.

## Coding Style & Naming Conventions
- Filenames: kebab‑case for Markdown/docs (`gpt5-agentic-workflow-guide.md`). Date‑prefix tickets/logs.
- Markdown: Title Case headings, short paragraphs, bullets first, links relative where possible.
- JSON: 2‑space indent, snake_case keys, deterministic field order. Include minimal examples.
- Code (when added): modules `snake_case`, types `PascalCase`, functions `snake_case`. Keep functions small and pure where practical.

## Testing Guidelines
- Co‑locate tests under `tests/` mirroring module paths. Targets: >80% coverage for analyzers and schema validators.
- Name tests `test_*.py` (Python) or `*_test.rs` (Rust). Keep fixtures small; store replay samples under `assets/replays/` (use Git LFS for large files).
- Include at least one “happy path” and one degraded/fallback case per feature.

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat(parser): add header-only fallback`.
- One logical change per PR; include description, rationale, and before/after artifacts (e.g., sample JSON output).
- Link to a ticket: `Relates-to: codex/tickets/2025-09-08-add-replay-parser.md`. Update docs/schemas alongside code.

## Security & Agent Notes
- Design is all‑local; avoid network calls in core analyzers. Do not commit large or sensitive replay files.
- For AI agents (Codex CLI): keep patches minimal, avoid unrelated reformatting, update plans as you work, and prefer adding targeted tests over broad refactors.
