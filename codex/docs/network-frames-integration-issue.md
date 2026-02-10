# Network Frames Integration Issue (2026-02-10)

## Current Status

- Previous failure mode was silent degradation (network frames available but parser quality not explicit).
- Current parser behavior is diagnostics-first: network parsing emits machine-readable diagnostics with `status` (`ok`, `degraded`, `unavailable`) plus `error_code`, `error_detail`, and `frames_emitted`.
- Corpus harness now exists at `scripts/parser_corpus_health.py` and reports aggregate reliability plus corpus metadata buckets.

## Corpus Gate Snapshot

Command:

```bash
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
```

Result on 2026-02-10:

- `total`: 202
- `header_success_rate`: 1.0
- `network_success_rate`: 0.995049504950495
- `degraded_count`: 1
- `top_error_codes`: `boxcars_network_error` (1)
- degraded replay: `replays/A181B28546BBD8AC71E63793B65BABAE.replay` (playlist bucket `tournament`)

## Decision Gate Outcome

Gate criteria from `codex/Plans/2026-02-10-parser-refactor-update-plan.md`:

- Go for non-boxcars backend if network success `< 99.5%`, or
- Go if any ranked-standard class has `>1%` degradation.

Current outcome (2026-02-10):

- Global threshold met (`99.50495% >= 99.5%`).
- Ranked-standard bucket (`inferred_3`) is `0/65` degraded.
- **No-Go** for secondary backend implementation at this time.

## References

- `scripts/parser_corpus_health.py`
- `codex/logs/2026-02-10-parser-perf-baseline.md`
- `codex/logs/2026-02-10-parser-backend-spike.md`
