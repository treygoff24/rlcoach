# Execution Prompt — Ticket 004: Parser Adapter Interface (Header + Network)

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; inspect files first; deterministic interfaces; explicit errors.
- No network in core logic; adapters must be local-only.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-004-parser-adapter-interface`

## Goal
- Define a pluggable parser interface supporting header-only and full network parsing modes, aligned with the plan’s “Parser Layer (local-only)”. Provide a null adapter that returns header-only fallback with a quality warning.

## Scope
- Add `src/rlcoach/parser/interface.py` with ABC:
  - `parse_header(path) -> Header`
  - `parse_network(path) -> NetworkFrames | None`
  - Data types: `Header`, `NetworkFrames` (minimal, typeddicts/dataclasses)
- Add `src/rlcoach/parser/null_adapter.py` implementing header-only fallback (populates minimal fields, sets quality warning `network_data_unparsed_fallback_header_only`).
- Add selection hook: `src/rlcoach/parser/__init__.py` exposing `get_adapter(name: str)` with default `null`.
- Tests asserting interface behavior and warning propagation.

## Out of Scope
- Actual Rocket League decode; Rust/Haskell adapters land in later tickets.

## Primary Files to Modify or Add
- `src/rlcoach/parser/interface.py`
- `src/rlcoach/parser/null_adapter.py`
- `src/rlcoach/parser/__init__.py`
- `tests/test_parser_interface.py`

## Implementation Plan
1) Introduce minimal data structures that map cleanly to the schema (playlist/map/team_size/goals/players for header; per-frame actor updates for network stubs).
2) Implement `null_adapter` returning header-only outputs and None for network.
3) Add tests verifying graceful degradation and warning tagging.

## Acceptance Checks (must pass)
- `pytest -q` passes; interface types importable; `get_adapter('null')` works.
- Calling `parse_network` on null adapter yields None; downstream code can branch accordingly.

## Validation Steps
- Run: `pytest -q`
- Manual: `python -c 'from rlcoach.parser import get_adapter; a=get_adapter("null"); print(a.parse_header("/tmp/foo.replay"))'`

## Deliverables
- Branch: `feat/gpt5-004-parser-adapter-interface`
- Files: parser interface, null adapter, tests
- Log: `./codex/logs/004.md`

## Safety & Compliance
- No network; explicit errors for unreadable files; typed structures.

---
