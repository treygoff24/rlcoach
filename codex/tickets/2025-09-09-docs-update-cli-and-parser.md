id: 2025-09-09
slug: docs-update-cli-and-parser
title: Ticket 2025-09-09 — Docs Update: CLI, Parser Build, Verification
branch: feat/gpt5-2025-09-09-docs
ticket_file: ./codex/tickets/2025-09-09-docs-update-cli-and-parser.md
log_file: ./codex/logs/2025-09-09-docs.md

## Objective
- Update docs to reflect the working Rust-backed parse + analyze flow, dev build steps, and quick verification commands.

## Scope
- `codex/docs/parser_adapter.md`:
  - Add `make rust-dev` flow, debug harness examples, and troubleshooting.
  - Note about optional dev downsampling flag and real replay gated test.
- `README.md`:
  - Add a quickstart: ingest, analyze, validate commands; expected output location and fields to check.
- Cross-link `codex/Plans/rlcoach_implementation_plan.md` where relevant.

## Out of Scope
- UI docs beyond a brief mention.

## Acceptance
- Docs are self-contained, up to date, and reflect the exact commands used to verify a successful run on a real replay.

## Deliverables
- Branch: feat/gpt5-2025-09-09-docs
- Files: `codex/docs/parser_adapter.md`, `README.md`
- Log: ./codex/logs/2025-09-09-docs.md

