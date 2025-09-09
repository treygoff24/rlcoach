id: 2025-09-09
slug: player-identity-enrichment
title: Ticket 2025-09-09 — Player Identity Enrichment (optional)
branch: feat/gpt5-2025-09-09-player-identity
ticket_file: ./codex/tickets/2025-09-09-player-identity-enrichment.md
log_file: ./codex/logs/2025-09-09-player-identity.md

## Objective
- Enrich player metadata from header properties (platform IDs, camera settings, loadouts) and surface them in the report `players[]` block as per schema.

## Scope
- Rust/Python parser headers: extract `UniqueId` (steam/epic/etc.), camera config, and loadouts when available; plumb through `Header` → report.
- Report generator: fill `players[].platform_ids`, `players[].camera`, `players[].loadout` with available values (keeping empty objects when unknown).
- Tests: small unit asserting keys are present (populated or empty) per schema.

## Out of Scope
- Any networking/data enrichment from external services.

## Acceptance
- For real replays where header properties are present, `players[]` includes non-empty platform IDs and/or camera settings.
- Schema validation continues to pass for cases where properties are missing (empty objects allowed).

## Deliverables
- Branch: feat/gpt5-2025-09-09-player-identity
- Files: parser header mapping (Rust or shim), `src/rlcoach/report.py`, tests
- Log: ./codex/logs/2025-09-09-player-identity.md

