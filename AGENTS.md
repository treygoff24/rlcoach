# RLCoach Agent Guide

Use this file as the entry point for `rlcoach`. Keep changes scoped, diagnostics-first, and aligned with the Python + Rust toolchain already in the repo.

## Critical Rule: Use The Virtual Environment

All direct Python commands must run inside `.venv`.

### Decision Table

| If you are running... | Use |
| --- | --- |
| `python`, `pytest`, project CLIs, one-off imports | `source .venv/bin/activate && ...` |
| Standard repo gates | `make ...` commands are preferred because they already handle the environment |

### Example Pattern

```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q
source .venv/bin/activate && python -m rlcoach.cli --help
```

Do not use system Python for repo work here.

## Task Router

| If the task is about... | Work here first | Load extra docs only if needed |
| --- | --- | --- |
| Core Python logic | `src/rlcoach` and matching `tests/` files | `README.md` for operator-facing behavior |
| Replay parser / Rust bridge | `parsers/rlreplay_rust` | Rust/build docs only if the bridge changes |
| Scope or roadmap changes | current plan in `codex/Plans/rlcoach_implementation_plan.md` | related ticket/docs only if the task expands scope |
| Design notes or tickets | `codex/docs/`, `codex/tickets/` | only the touched note/ticket |
| Replay fixtures | `assets/replays/` | Git LFS workflow as needed |
| Schemas | `schemas/` | matching tests/fixtures |

Do not read all of `codex/` or all planning docs for a local bug fix.

## Working Workflow

1. Identify the owning module and matching tests.
2. Activate `.venv` before any direct Python command.
3. Read the touched source file, neighboring tests, and only the plan/ticket doc that directly governs the task.
4. Make the smallest coherent change.
5. Run narrow tests first, then broader repo checks if the change crosses boundaries.

## Verification Table

| Change type | Start with | Broaden to |
| --- | --- | --- |
| Python logic or analyzer behavior | `source .venv/bin/activate && PYTHONPATH=src pytest tests/... -q` | `make test` |
| Formatting/lint cleanup | `make fmt`, `make lint` | combine with relevant tests |
| Rust bridge changes | relevant Rust/Python bridge checks | `make test` plus bridge-specific validation |
| CLI/report behavior | targeted CLI invocation plus matching tests/goldens | `make test` |

## Repo Rules

- Mirror new source modules with matching tests under `tests/`.
- Keep large replay fixtures in `assets/replays/` through Git LFS.
- Prefer targeted tests over broad refactors.
- Analysis stays local. Do not add remote/network behavior to parsers or analyzers.
- Update docs and schemas alongside behavior changes when those outputs are user-facing contracts.

## Analysis Conventions

- Analysis modules live under `src/rlcoach/analysis/`.
- Expensive analyzers are cached at the aggregator level; preserve that pattern rather than recomputing heavy analysis repeatedly.
- Analyzer outputs should stay consistent and predictable across modules.

## Do This, Not That

- Do use `.venv` for direct Python commands. Do not call bare `python`, `python3`, or `pytest` and hope the shell is configured.
- Do update matching tests and goldens when contracts change. Do not treat fixtures or Markdown outputs as disposable.
- Do use `README.md` and the active plan doc when operator behavior or scope is in play. Do not default to reading the whole `codex/` tree.
