# Execution Prompt — Ticket 003: File Ingestion and Validation

You are a coding agent in Codex CLI. Plan–execute–verify until all acceptance checks pass.

## Critical Rules (repeat)
- Persist; read before changing; small diffs; explicit errors.
- Determinism: stable names, atomic writes; no hidden state.
- Safety: no network for core logic; no secrets; local files only.

## Environment & Tools
- Agent context: Codex CLI
- Tools: plan, shell, apply_patch, pytest
- Approvals: never; Network: enabled; Filesystem: full

## Branching
- Base: main
- Create: `feat/gpt5-003-ingestion-validation`

## Goal
- Implement robust local ingestion for `*.replay` files: safe open, file hashing, size bounds, basic header CRC gate (stub acceptable pending parser), and explicit degradation to header-only mode as per plan A.

## Scope
- Add `src/rlcoach/ingest.py` with:
  - `read_replay_bytes(path) -> bytes`
  - `file_sha256(path) -> str`
  - `bounds_check(size_bytes)`, constants for sane size thresholds
  - `crc_check_header(data: bytes) -> (ok: bool, detail: str)` (stub allowed now)
- Add `src/rlcoach/errors.py` with typed exceptions and precise messages.
- CLI: extend `src/rlcoach/cli.py` with `ingest <path>` printing hash, size, and CRC result.
- Tests for happy path, missing file, too-large, and CRC-fail (stubbed).

## Out of Scope
- Full header parse or network parsing; handled in later tickets.

## Primary Files to Modify or Add
- `src/rlcoach/ingest.py` — I/O + checks
- `src/rlcoach/errors.py` — exceptions/messages
- `src/rlcoach/cli.py` — `ingest` subcommand
- `tests/test_ingest.py` — unit tests

## Implementation Plan
1) Add ingestion helpers with careful error handling; return explicit error details.
2) Wire CLI subcommand; add structured outputs for machine readability where helpful.
3) Add tests covering bounds and error surfaces; use temp files for fixtures.

## Acceptance Checks (must pass)
- `pytest -q` passes (includes 4+ ingestion tests).
- `python -m rlcoach.cli ingest /tmp/foo.replay` prints hash/size and a CRC check result.
- Errors show actionable messages (path, reason, suggested next step).

## Validation Steps
- Run: `pytest -q`
- Manual: create small temp file and run CLI; verify output.

## Deliverables
- Branch: `feat/gpt5-003-ingestion-validation`
- Files: ingest/errors modules, CLI updates, tests
- Log: `./codex/logs/003.md`

## Safety & Compliance
- No network in core; do not read outside provided path; fail fast on bad input.

---
