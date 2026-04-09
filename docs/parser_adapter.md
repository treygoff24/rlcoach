# Parser Adapter Contract

Canonical path: `docs/parser_adapter.md`.

This document defines the runtime contract between the parser bridge, normalization layer, event detectors, and report output.

## Build And Dev Workflow

Use the project virtual environment for every Python command:

```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q
source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test
source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop
```

## Current Backend Posture

- Default backend policy is diagnostics-first with explicit degradation.
- `null` adapter remains a header-only fallback.
- `rust` adapter remains the primary network-data backend (boxcars + pyo3).
- Network failures must produce structured diagnostics, never silent fallback.
- JSON, Markdown, and corpus-health surfaces report parser scorecard coverage as current behavior.
- JSON and Markdown reports surface parser diagnostics plus scorecard coverage for the selected backend.

## Header Contract

The parser header contract includes:

- `playlist_id`, `map_name`, `team_size`
- `engine_build`, `match_guid`, `overtime`, `mutators`
- `team0_score`, `team1_score`, `match_length`
- `players`, `goals`, `highlights`
- `quality_warnings`

When fields are unavailable, the adapter degrades with explicit warnings and leaves optional values unset.

## Network Frame Contract

Each frame should carry:

- `timestamp`
- `ball`
- `players`
- `boost_pad_events`
- `parser_touch_events`
- `parser_demo_events`
- `parser_tickmarks`
- `parser_kickoff_markers`

Player component-state flags are tri-state semantically:

- `True`: parser explicitly observed active state
- `False`: parser explicitly observed inactive state
- `None`: parser could not provide authority for that field

## Parser Event Streams

The parser-facing event carriers on each frame are:

- `parser_touch_events`
- `parser_demo_events`
- `parser_tickmarks`
- `parser_kickoff_markers`

Event detectors consume parser events first when present, then use existing inference fallbacks when absent.

Corpus-health tracks parser event/provenance coverage across these carriers:

- `parser_event_coverage` reports touch, demo, tickmark, and kickoff-marker replay/frame coverage.
- `event_provenance` reports parser-vs-inferred prevalence for touch, demo, and kickoff event surfaces where provenance is observable.
- `parser_event_totals` and `parser_event_source_counts` preserve the raw aggregate event counts.

Parser event `source` values preserve provenance. Parser-authored carriers should use `source="parser"`; inferred downstream events retain `source="inferred"` when parser authority is absent.

## Diagnostics And Degradation Semantics

`network_diagnostics` must preserve:

- `status`
- `error_code`
- `error_detail`
- `frames_emitted`
- `attempted_backends`

Degraded and unavailable states are valid outputs and are expected in corpus-health reporting.

`scorecard` and `scorecard_coverage` fields measure whether parser output is usable for downstream analysis; the exact fields are listed below.

## Scorecard And Corpus-Health Semantics

Reports include `quality.parser.scorecard` with:

- `usable_network_parse`
- `non_empty_player_frame_coverage`
- `player_identity_coverage`
- `network_frame_count`
- `non_empty_player_frames`
- `players_with_identity`
- `expected_players`

The corpus harness extends those per-report scorecard semantics across replay roots and also reports:

- `scorecard_coverage`
- `parser_event_totals`
- `parser_event_coverage`
- `parser_event_source_counts`
- `event_provenance`

Invalid replay roots fail explicitly with `invalid_replay_root`; valid roots with no `.replay` files fail explicitly with `no_replays_found`.

## Test And Corpus-Health Commands

Core parser-analysis validation:

```bash
source .venv/bin/activate && PYTHONPATH=src pytest \
  tests/test_rust_adapter.py \
  tests/parser/test_rust_adapter_smoke.py \
  tests/test_parser_interface.py \
  tests/test_normalize.py \
  tests/test_events.py \
  tests/test_events_calibration_synthetic.py \
  tests/test_analysis_mechanics_contract.py \
  tests/test_analysis_mechanics_advanced.py \
  tests/test_schema_validation.py \
  tests/test_schema_validation_hardening.py \
  tests/test_docs_parser_contract.py \
  tests/test_benchmarks.py -q
```

Corpus-health gate:

```bash
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
```
