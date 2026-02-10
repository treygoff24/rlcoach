# Network Frames Integration Report (2026-02-10)

## Scope

This report records the Task 12 verification/doc outcome for parser reliability and backend decision gating.

## Behavior Verification

- Rust adapter now surfaces explicit network diagnostics (`ok|degraded|unavailable`) instead of relying on implicit fallback semantics.
- Corpus health harness added (`scripts/parser_corpus_health.py`) with JSON schema containing:
  - `total`
  - `header_success_rate`
  - `network_success_rate`
  - `degraded_count`
  - `top_error_codes`
  - corpus metadata buckets (`playlist`, `match_type`, `engine_build`)

## Corpus Results (2026-02-10)

- Total replays: 202
- Header success rate: 1.0
- Network success rate: 0.995049504950495
- Degraded count: 1
- Top error code: `boxcars_network_error` (1)
- Degraded replay class: tournament 2v2 (`replays/A181B28546BBD8AC71E63793B65BABAE.replay`)

## Backend Decision Gate

Criteria:

- Go if global network success `<99.5%`.
- Go if any ranked-standard class has `>1%` degradation.

Observed:

- Global success is `99.50495%` (passes threshold).
- Ranked-standard (`inferred_3`) is `0/65` degraded (passes class threshold).

Decision:

- **No-Go** for non-boxcars backend implementation.
- Keep existing backend seam and continue monitoring with corpus harness.

## Linked Logs

- `codex/logs/2026-02-10-parser-perf-baseline.md`
- `codex/logs/2026-02-10-parser-backend-spike.md`
