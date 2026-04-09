# Network Frames Integration Issue (updated 2026-04-09)

## Current Status

- Previous failure mode was silent degradation (network frames available but parser quality not explicit).
- Current parser behavior is diagnostics-first: network parsing emits machine-readable diagnostics with `status` (`ok`, `degraded`, `unavailable`) plus `error_code`, `error_detail`, and `frames_emitted`.
- Canonical parser contract path: `docs/parser_adapter.md`.
- Corpus harness now exists at `scripts/parser_corpus_health.py` and reports aggregate reliability, scorecard coverage, parser event coverage, parser-vs-inferred provenance, and corpus metadata buckets.

## Corpus Gate Snapshot

Command:

```bash
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
```

Result on 2026-04-09:

- `total`: 202
- `header_success_rate`: 1.0
- `network_success_rate`: 0.995049504950495
- `usable_network_parse_rate`: 0.9801980198019802
- `avg_non_empty_player_frame_coverage`: 0.9798575609006099
- `avg_player_identity_coverage`: 0.995049504950495
- `avg_parser_event_frame_coverage`: 0.014774534741432225
- `scorecard_coverage`: usable_network_parse_rate=0.9801980198019802, avg_non_empty_player_frame_coverage=0.9798575609006099, avg_player_identity_coverage=0.995049504950495
- `parser_event_coverage`: touch_event_rate=0.995049504950495, demo_event_rate=0.8811881188118812, tickmark_event_rate=0.995049504950495, kickoff_marker_rate=0.9900990099009901
- `event_provenance`: touch_parser_rate=1.0, demo_parser_rate=1.0, kickoff_parser_rate=1.0
- `degraded_count`: 1
- `top_error_codes`: `boxcars_network_error` (1)
- `parser_event_totals`: touches=21178, demos=725, tickmarks=2142, kickoff_markers=2158
- `parser_event_source_counts`: parser=26203, inferred=0, missing=0, other=0
- degraded replay: `replays/A181B28546BBD8AC71E63793B65BABAE.replay` (playlist bucket `tournament`)

## Decision Gate Outcome

Gate criteria from `codex/Plans/2026-02-10-parser-refactor-update-plan.md`:

- Go for non-boxcars backend if network success `< 99.5%`, or
- Go if any ranked-standard class has `>1%` degradation.

Current outcome (2026-04-09):

- Global threshold met (`99.50495% >= 99.5%`).
- Ranked-standard bucket (`inferred_3`) is `0/65` degraded.
- **No-Go** for secondary backend implementation at this time.

## Discovery Error Contract

The corpus harness no longer reports a silent empty success for bad input:

- invalid roots return `invalid_replay_root` with exit code 2
- valid roots containing no `.replay` files return `no_replays_found` with exit code 3

## References

- `docs/parser_adapter.md`
- `scripts/parser_corpus_health.py`
- `codex/logs/2026-02-10-parser-perf-baseline.md`
- `codex/logs/2026-02-10-parser-backend-spike.md`
