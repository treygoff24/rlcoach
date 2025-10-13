# 0925 Ballchasing Parity Plan

## Goals
- Establish a reusable harness that diff compares rlcoach JSON against Ballchasing CSV exports for local fixtures.
- Normalize player identities so canonical `{platform}:{account}` keys align across Ballchasing and rlcoach.
- Surface metric deltas with tolerances to steer analyzer backlog (movement, boost, kickoff specifics).

## Identity Strategy
- Prefer platform identifiers (`steam`, `psn`, `xbox`, `epic`) when provided; derive canonical IDs as `{platform}:{id}`.
- Sanitize display names (trim, collapse whitespace, NFKC normalize) and generate slug fallbacks (`slug:player-name`) when platform IDs are missing.
- Maintain alias lookup (`player_0`, raw actor IDs, slug) to keep analyzers and events aligned with canonical IDs.
- Report generator consumes the identity map so `players[*].player_id` and analyzer outputs match the parity harness inputs.

## Parity Harness Outline
- Sources:
  - rlcoach JSON generated via `python -m rlcoach.cli report-md Replay_files/0925.replay --out out --pretty`.
  - Ballchasing CSV exports stored under `Replay_files/ballchasing_output/`.
- Helpers (`src/rlcoach/utils/parity.py`):
  - CSV loaders normalize platform labels, coerce numeric metrics, and retain sanitized names.
  - Flattened rlcoach extractors provide comparable per-player and per-team metric dictionaries.
  - `collect_metric_deltas` applies metric tolerances and formats actionable rows.
- Test (`tests/analysis/test_ballchasing_parity.py`):
  - Validates fixture availability, asserts identity coverage, and xfails with a delta summary while analyzers diverge.
  - Tolerances tuned to highlight large gaps (movement speed buckets, supersonic time, kickoff metrics) without noisy churn.

## Iteration Notes
- Next passes should bring boost/movement analyzers into parity, then tighten tolerances toward Ballchasing deltas <5%.
- Kickoff outcome parity is still gated on richer event tagging; harness already lists the mismatch for tracking.
- Once parity narrows, flip the test from xfail to assert to gate regressions.
