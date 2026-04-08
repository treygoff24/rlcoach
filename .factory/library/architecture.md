# Architecture

How the Rust parser completion mission works at a high level.

**What belongs here:** parser/report architecture, component relationships, data flow, invariants, and mission-critical decision points.
**What does NOT belong here:** exact command lists or port usage (use `.factory/services.yaml`), feature sequencing (use `features.json`), or temporary implementation notes.

---

## System Overview

RLCoach processes Rocket League replays through a local-only pipeline:

1. **CLI entrypoints** accept a replay path and analysis mode.
2. **Parser adapters** extract replay metadata and, when available, network/frame data.
3. **Normalization** converts parser output into typed frame/player/event structures.
4. **Event detectors** build goals, demos, kickoffs, touches, boost pickups, and timeline events.
5. **Analysis modules** compute per-player and per-team metrics, including advanced mechanics.
6. **Report generation** emits schema-valid JSON and paired Markdown dossiers.
7. **Corpus-health tooling** measures parser reliability and coverage over the local replay corpus.

The Rust parser mission strengthens the parser and every downstream consumer that depends on parser authority.

## Major Components

### CLI Layer
- `python -m rlcoach.cli analyze ...`
- `python -m rlcoach.cli report-md ...`
- `python scripts/parser_corpus_health.py ...`

These are the primary validation surfaces for this mission. The mission is complete only when these surfaces reflect the finished parser contract.

### Parser Layer
Key files:
- `src/rlcoach/parser/interface.py`
- `src/rlcoach/parser/types.py`
- `src/rlcoach/parser/rust_adapter.py`
- `src/rlcoach/parser/null_adapter.py`
- `parsers/rlreplay_rust/src/lib.rs`
- selection entrypoints in `src/rlcoach/parser/__init__.py` and `src/rlcoach/cli.py`

- **Rust adapter** is the primary rich parser path.
- **Null/header-only paths** remain valid degraded modes.
- Adapter selection is observable through CLI flags such as `--adapter rust`, `--adapter null`, and `--header-only` behavior.
- Parser diagnostics are explicit and machine-readable; parser failures must never become silent success.

The parser layer owns:
- header metadata breadth
- network/frame extraction
- parser-authored event carriers
- parser diagnostics and provenance
- the typed parser contract that downstream Python code consumes

Parser → normalization contract:
- parser outputs are carried through the typed contract in `parser/types.py`
- the important boundary objects are header data, network diagnostics, raw frame/player payloads, and parser-authored event collections
- workers should treat that typed contract as the canonical shape; do not invent parallel ad hoc payload structures

### Normalization Layer
Key files:
- `src/rlcoach/normalize.py`
- typed parser boundary structures from `src/rlcoach/parser/types.py`

Normalization converts parser output into typed structures that downstream code can consume without reparsing raw dicts.

It must preserve:
- explicit boolean semantics (`True` / `False` / `None`)
- parser-authored event collections
- provenance/source information
- score/team/player referential integrity

Normalization → events contract:
- event detectors should consume normalized frame/player/event structures, not raw parser payloads
- parser-authored carriers must survive normalization intact enough for event detectors to make parser-first decisions

### Event Layer
Key files:
- `src/rlcoach/events/touches.py`
- `src/rlcoach/events/demos.py`
- `src/rlcoach/events/goals.py`
- `src/rlcoach/events/kickoffs.py`
- `src/rlcoach/events/boost.py`
- `src/rlcoach/events/timeline.py`
- supporting types/helpers in `src/rlcoach/events/types.py`, `src/rlcoach/events/utils.py`, and related modules

Event detectors consume normalized data and must prefer parser authority when available.

Event-layer invariants:
- parser-first, heuristic-fallback second
- no double-counting between authoritative and inferred events
- emitted events keep source/provenance visible
- timeline ordering remains monotonic and consistent with event collections

### Analysis Layer
Key files:
- `src/rlcoach/analysis/mechanics.py`
- `src/rlcoach/analysis/__init__.py`
- other analysis modules under `src/rlcoach/analysis/`

The analysis layer computes report metrics from normalized frames/events.

For this mission, the most important analysis surface is **mechanics**:
- advanced mechanic keys must exist in the final output surface
- derived totals must remain internally consistent
- parser-authoritative signals should improve mechanics accuracy where available
- team-level rollups must stay aligned with per-player outputs
- the aggregator in `analysis/__init__.py` remains the integration point for per-player and per-team analysis output

### Report Layer
Key files:
- `src/rlcoach/report.py`
- `src/rlcoach/report_markdown.py`
- `schemas/replay_report.schema.json`

The report layer is the contract boundary consumed by validation.

It must:
- emit schema-valid JSON
- preserve parser diagnostics and scorecard data
- surface completed mechanics/report fields consistently
- keep Markdown and JSON aligned

### Corpus-Health Layer
Key files:
- `scripts/parser_corpus_health.py`
- related parser benchmark/reliability tests under `tests/test_benchmarks.py`

Corpus-health is the reliability boundary for the parser.

It must continue to report:
- header success
- network success
- degraded count
- usable parse rate
- top error codes

And, once implemented by the mission, it must also report parser event/provenance coverage required by the finished contract. For this mission, workers should treat event/provenance coverage as coverage metrics over the final parser contract surfaces (for example, whether the corpus exposes the completed authoritative event/provenance outputs often enough to measure them explicitly), not as an invitation to invent unrelated health metrics.

## Data Flow

Key orchestration files:
- `src/rlcoach/ingest.py`
- `src/rlcoach/pipeline.py`
- `src/rlcoach/cli.py`

```text
Replay file
  -> ingest / CLI command
  -> parser adapter (rust / null / header-only)
  -> parser diagnostics + header + frames/events
  -> normalization into typed structures
  -> event preference / fallback logic
  -> analysis aggregation
  -> JSON report / Markdown dossier / corpus summary
```

`pipeline.py` is the runtime glue that connects parser output to normalization, events, analysis, and report generation. Workers changing cross-layer behavior should verify that the pipeline still preserves the intended data flow end-to-end.

## Mission-Critical Invariants

1. **Diagnostics-first behavior**
   - degraded or unavailable parser behavior must remain explicit
   - no silent fallback that disguises parser problems as healthy parses

2. **Backward-compatible degradation paths**
   - `--header-only` and `--adapter null` remain supported validation surfaces
   - degraded outputs must stay schema-valid and observable

3. **Authoritative-first downstream consumption**
   - when parser authority exists, consumers should use it before heuristics
   - fallback remains documented and provenance-visible

4. **Schema/report parity**
   - JSON schema, JSON output, and Markdown output must describe the same shipped behavior
   - newly completed parser/mechanics fields must not appear in one surface and disappear in another

5. **Local-only verification**
   - mission validation must work without external services
   - replay corpus, Rust toolchain, Python venv, and local CLI flows are sufficient

## Touch-Authority Decision Gate

Touch authority is a mission-level decision point.

Acceptable final states:
- **Parser-native touch authority:** Rust parser emits touch events used downstream with parser provenance.
- **Documented inference-backed contract:** if parser-native touch authority is not feasible, the system must explicitly surface the fallback contract and provenance instead of pretending touch authority exists.

Either outcome must be observable in validation and documentation.

## Shared Operational Constraints

- The mission must not depend on Docker.
- The mission must not require long-running local services.
- Workers should validate through CLI/test/corpus surfaces rather than web/API infrastructure.
- Existing unrelated services/ports in the user environment are off-limits.
