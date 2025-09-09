id: 2025-09-09
slug: ci-rust-build-and-smoke-tests
title: Ticket 2025-09-09 — CI: Rust Build + Adapter Smoke Tests
branch: feat/gpt5-2025-09-09-ci-rust
ticket_file: ./codex/tickets/2025-09-09-ci-rust-build-and-smoke-tests.md
log_file: ./codex/logs/2025-09-09-ci-rust.md

## Objective
- Add CI job to install Rust + maturin, build the `rlreplay_rust` wheel, install it, and run adapter smoke tests.
- Keep CI fast; gate real replay tests behind an environment flag.

## Scope
- CI config (GitHub Actions or equivalent):
  - Install Rust toolchain and Python; cache cargo/pip where possible.
  - `make rust-dev` (or equivalent steps) to build and install the extension.
  - Run a subset of tests including `tests/parser/test_rust_adapter_smoke.py` and schema tests.
- Tests:
  - Ensure smoke tests skip gracefully if Rust core fails to import (still pass overall without hard failing the suite).

## Out of Scope
- Running analyze on large replays in CI (time/cost); covered by gated test ticket.

## Acceptance
- CI job green on main branch and PRs.
- Build log shows Rust extension built and importable; smoke test executes (or skips consistently without failing) and reports 0 failures.

## Deliverables
- Branch: feat/gpt5-2025-09-09-ci-rust
- Files: CI workflow files under `.github/workflows/*` (or project CI), docs update if needed.
- Log: ./codex/logs/2025-09-09-ci-rust.md

