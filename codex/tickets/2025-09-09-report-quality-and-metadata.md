id: 2025-09-09
slug: report-quality-and-metadata
title: Ticket 2025-09-09 — Report Quality Signals & Metadata Fidelity
branch: feat/gpt5-2025-09-09-report-quality
ticket_file: ./codex/tickets/2025-09-09-report-quality-and-metadata.md
log_file: ./codex/logs/2025-09-09-report-quality.md

## Objective
- Standardize quality warnings and ensure metadata fidelity in the final JSON.
- Ensure `quality.parser.parsed_network_data` truthfully reflects frame presence; remove placeholder “stub” warnings.

## Scope
- Report generator (`src/rlcoach/report.py`):
  - Set `parsed_network_data` based on actual frames length.
  - De-duplicate and sanitize `quality.warnings`; replace any `*_stub` with more accurate signals.
  - Fill `metadata.map`, `team_size`, `duration_seconds`, `total_frames`, `recorded_frame_hz` from header/normalized frames where available.
  - Ensure player blocks (`players[]`, `teams.blue/orange.players`) reflect header names and team assignment in stable order.
- Schema validation (`src/rlcoach/schema.py`):
  - No changes expected; ensure validations pass for updated payload.

## Out of Scope
- Changing schema structure.
- Parser internals; see Rust parse stabilization ticket.

## Acceptance
- An analyze run on a real replay produces a payload where:
  - `quality.parser.parsed_network_data == true` when frames exist.
  - `quality.warnings` contains `parsed_with_rust_core` only (no `*_stub`).
  - `metadata.total_frames` and `recorded_frame_hz` are non-default and plausible; `players[]` names match header.
  - `schemas/replay_report.schema.json` validation passes via `validate_report`.

## Deliverables
- Branch: feat/gpt5-2025-09-09-report-quality
- Files: `src/rlcoach/report.py`
- Log: ./codex/logs/2025-09-09-report-quality.md

