# Execution Prompt — Ticket 013: Rust Parser Adapter (pyo3) — Header + Network

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; read first; deterministic FFI; explicit errors; minimal diffs.
- Network allowed for toolchain/crates; no secrets.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full


## Goal
- Implement a Rust parser adapter compiled as a Python module via `pyo3`, capable of header parse (playlist/map/team_size/goals/players) and a minimal network frame iterator. Wire it behind `get_adapter('rust')`.

## Scope
- Add `parsers/rlreplay_rust/` crate with `Cargo.toml`, `src/lib.rs` using `pyo3`.
- Expose functions: `parse_header(path) -> PyDict`, `iter_frames(path) -> iterator` (yield minimal frame dicts).
- Python shim `src/rlcoach/parser/rust_adapter.py` wrapping the module to fit interface.
- Build instructions in `docs/parser_adapter.md` (toolchain setup, build commands).
- Tests validating header fields on tiny fixture or synthetic file.

## Out of Scope
- Full physics fidelity; UI; performance tuning.

## Primary Files to Modify or Add
- `parsers/rlreplay_rust/Cargo.toml`, `parsers/rlreplay_rust/src/lib.rs`
- `src/rlcoach/parser/rust_adapter.py`
- `src/rlcoach/parser/__init__.py` (register adapter)
- `docs/parser_adapter.md`
- `tests/test_rust_adapter.py`

## Implementation Plan
1) Scaffold pyo3 crate with minimal parse stubs (ok to return placeholder network frames initially).
2) Build locally; publish wheel to local env; import from Python and adapt to interface.
3) Add tests asserting header extraction and adapter selection.

## Acceptance Checks (must pass)
- `pytest -q` passes; `get_adapter('rust')` imports and parses header fields.
- Build steps documented and reproducible locally.

## Validation Steps
- Build: `cd parsers/rlreplay_rust && cargo build --release` (or maturin)
- Run: `pytest -q`

## Deliverables
- Files: rust crate, python shim, tests, docs
- Log: `./codex/logs/013.md`

## Safety & Compliance
- No network during parse; only for toolchain/crates. Clear errors on unreadable files.

---
