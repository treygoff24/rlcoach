id: 2025-09-09
slug: dev-sampling-flag
title: Ticket 2025-09-09 — Developer Sampling Flag for Faster Analyzes (optional)
branch: feat/gpt5-2025-09-09-dev-sampling
ticket_file: ./codex/tickets/2025-09-09-dev-sampling-flag.md
log_file: ./codex/logs/2025-09-09-dev-sampling.md

## Objective
- Add an optional environment flag to downsample frames during analysis in development, reducing runtime on long replays without changing default behavior.

## Scope
- Report/normalize path:
  - If `RLCOACH_SAMPLE_EVERY=N` is set (e.g., 2 or 3), sample every Nth frame after parsing and before event detection.
  - Ensure this flag is clearly marked as dev-only; inject a `quality.warnings` note (e.g., `analysis_downsampled_n=2`).
- Docs: describe usage in `codex/docs/parser_adapter.md` or README’s dev section.

## Out of Scope
- Changing defaults or affecting released behavior.

## Acceptance
- With `RLCOACH_SAMPLE_EVERY=3`, analysis completes faster and the warning appears in `quality.warnings`.
- Without the env var, behavior is unchanged.

## Deliverables
- Branch: feat/gpt5-2025-09-09-dev-sampling
- Files: `src/rlcoach/report.py` (sampling hook), docs update
- Log: ./codex/logs/2025-09-09-dev-sampling.md

