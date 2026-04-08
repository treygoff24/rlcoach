# Parser Adapter Contract

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

## Diagnostics And Degradation Semantics

`network_diagnostics` must preserve:

- `status`
- `error_code`
- `error_detail`
- `frames_emitted`
- `attempted_backends`

Degraded and unavailable states are valid outputs and are expected in corpus-health reporting.

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
