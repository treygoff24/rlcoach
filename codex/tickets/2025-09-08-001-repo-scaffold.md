# Execution Prompt — Ticket 001: Initialize Repo Scaffold

You are a coding agent working in Codex CLI. Run a plan–execute–verify loop, use tools to inspect and modify files (don’t guess), and continue until every acceptance check passes.

## Critical Rules (repeat)
- Persist; read first; small, focused diffs.
- Use planning, shell, and patch tools with concise preambles.
- Determinism: stable paths/names; atomic writes; schema/versioning.
- Safety: no secrets; no network unless this ticket allows it.
- Style: follow repo AGENTS.md; keep changes minimal and scoped.
- Observability: explicit, actionable errors and logs.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan tool, shell, apply_patch, test runner
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-001-repo-scaffold`

## Goal
- Bootstrap a Python-first project skeleton for rlcoach with deterministic local development: src/tests layout, schemas dir, Makefile, basic tooling (pytest, ruff, black), and a minimal package entrypoint.

## Scope
- Add `pyproject.toml` (pytest, ruff, black), `Makefile`, `src/rlcoach/__init__.py`, `src/rlcoach/cli.py` (stub), `tests/test_smoke.py`, `schemas/.keep`.
- Add `.gitignore` and `README.md` skeleton linking to `codex/Plans/rlcoach_implementation_plan.md`.

## Out of Scope
- Parser, analyzers, and schema content; UI; replay assets.

## Primary Files to Modify or Add
- `pyproject.toml` — project metadata, deps (pytest, ruff, black)
- `Makefile` — `test`, `fmt`, `lint`
- `src/rlcoach/cli.py` — stub CLI with `--version`
- `tests/test_smoke.py` — asserts CLI runs
- `schemas/.keep` — placeholder
- `.gitignore` — Python, build artifacts

## Implementation Plan
1) Create Python package scaffold and tool configs.
2) Wire Make targets and basic CLI stub.
3) Add smoke test and run locally.
4) Document commands in README.

## Acceptance Checks (must pass)
- `make test` runs `pytest -q` and passes.
- `make fmt` formats; `make lint` runs ruff with zero errors on new files.
- `python -m rlcoach.cli --version` prints a semantic version.

## Validation Steps
- Lint/Format: `make fmt && make lint`
- Tests: `make test`
- Smoke: `python -m rlcoach.cli --help`

## Deliverables
- Branch: `feat/gpt5-001-repo-scaffold`
- Files: pyproject, Makefile, src/, tests/, schemas/
- Log: `./codex/logs/001.md` summarizing steps and results

## Commit & PR Guidance
- Small commits, imperative messages; include commands and outputs from validations.

## Safety & Compliance
- No secrets; no large binaries; network only for installing dev tools.

## Observability & Logging
- CLI should print clear help and version; tests/log output concise.

---
