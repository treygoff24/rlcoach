# Repository Guidelines

## Project Structure & Module Organization
Core logic resides in `src/rlcoach`, grouped by ingest, parsing, events, analysis, and reporting stages; mirror any new module with a counterpart under `tests/`. The Rust replay bridge lives in `parsers/rlreplay_rust` and is compiled alongside Python bindings. Planning docs stay in `codex/Plans/`—always review `codex/Plans/rlcoach_implementation_plan.md` before proposing scope changes. Use `codex/docs/` for design notes, `codex/logs/` for session journals, and `codex/tickets/` (kebab-case filenames) for work items. Large fixture replays belong in `assets/replays/` and must go through Git LFS; JSON schemas reside in `schemas/`.

## Build, Test, and Development Commands
Run `make install-dev` on first setup to install Black, Ruff, pytest, and maturin helpers. `make test` (or `pytest -q`) executes the full suite; target focused files with `pytest tests/test_ingest.py -q` when iterating. Use `make fmt` for Black formatting and `make lint` for Ruff. Rebuild the Rust adapter with `make rust-dev` before validating parser changes, and `make clean` clears caches when test state drifts.

## Markdown Report Generation
Use `python -m rlcoach.cli report-md path/to/replay.replay --out out --pretty` to produce both the JSON schema payload and the Markdown dossier in one call. The command writes `<stem>.json` and `<stem>.md` atomically; the Markdown composer can still emit an error summary when parsing fails. Golden fixtures under `tests/goldens/*.md` illustrate the expected table layout.

## Coding Style & Naming Conventions
Python code follows Black (88 columns) and Ruff defaults; prefer compact, pure functions and explicit return types. Modules, functions, and variables use `snake_case`; classes use `PascalCase`; constants are upper snake. Markdown headings are Title Case and files use kebab-case. JSON artifacts use 2-space indentation, snake_case keys, and deterministic field ordering—include minimal, real-sample payloads in docs.

## Testing Guidelines
All tests run under pytest; name files `test_*.py` mirroring the `src/` tree. Provide both successful and degraded scenarios (e.g., header-only fallback) for new analyzers or ingest paths. Maintain ≥80% coverage for analyzers and schema validators, and store shared replay fixtures in `assets/replays/`.

## Commit & Pull Request Guidelines
Use Conventional Commits such as `feat(parser): add kickoff outcomes`. Keep each PR focused, document rationale and before/after JSON snippets, and link tickets with `Relates-to: codex/tickets/yyyy-mm-dd-title.md`. Update related docs and schemas alongside code, and include `make test` results in the PR description.

## Security & Agent Notes
Analysis stays fully local—avoid remote calls in parsers or analyzers. Do not commit raw ladder replays; reference Git LFS pointers instead. Codex CLI agents must log progress in `codex/logs/`, refresh the active plan if scope shifts, and prefer targeted tests over broad refactors to match repository expectations.
