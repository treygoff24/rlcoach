id: 2025-09-09
slug: pyo3-deprecations-cleanup
title: Ticket 2025-09-09 — PyO3 Deprecations Cleanup (optional)
branch: feat/gpt5-2025-09-09-pyo3-cleanup
ticket_file: ./codex/tickets/2025-09-09-pyo3-deprecations-cleanup.md
log_file: ./codex/logs/2025-09-09-pyo3-cleanup.md

## Objective
- Remove or update deprecated PyO3 API usage in the Rust core to prevent future build warnings and ensure forward compatibility.

## Scope
- Update `parsers/rlreplay_rust/src/lib.rs` to use current PyO3 idioms for constructing Python dicts/lists and returning iterables.
- Run a release build to ensure no deprecation warnings remain.

## Out of Scope
- Functional changes to parsing logic.

## Acceptance
- `cargo build --release` (or maturin build) emits no PyO3 deprecation warnings.

## Deliverables
- Branch: feat/gpt5-2025-09-09-pyo3-cleanup
- Files: `parsers/rlreplay_rust/src/lib.rs`
- Log: ./codex/logs/2025-09-09-pyo3-cleanup.md

