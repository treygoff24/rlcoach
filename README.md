# rlcoach

All-local Rocket League replay analysis tool for comprehensive performance coaching.

## Overview

rlcoach is designed to provide detailed analysis of Rocket League replays without requiring any cloud services or network connectivity. The tool processes .replay files locally and generates comprehensive JSON reports with player performance metrics, team analysis, and coaching insights.

## Project Status

- End-to-end CLI pipeline (ingest -> normalize -> events -> analyzers -> JSON/Markdown) is implemented with 261 tests.
- Parser adapters are pluggable:
  - `null` adapter (header-only fallback; always available)
  - optional `rust` adapter (pyo3 + boxcars) for richer header parsing and network frames
- Rust parser behavior is diagnostics-first: degraded/unavailable network parses emit explicit machine-readable diagnostics instead of silent fallback.
- Corpus reliability gate (2026-02-10): on 202 local replays, header success was 100%, network success was 99.50%, with 1 degraded replay (`boxcars_network_error`).
- 14 analysis modules covering fundamentals, boost, movement, positioning, mechanics, defense, xG, and more.
- Markdown dossier generator mirrors the JSON schema and ships with golden fixtures.
- Offline CLI viewer renders summaries from previously generated JSON reports.

See the [implementation plan](codex/Plans/rlcoach_implementation_plan.md) for scope and roadmap.

## Quick Start

### Installation

```bash
# Install development dependencies
make install-dev

# (Optional) Build the Rust replay adapter
make rust-dev
```

### Usage

```bash
# CLI help / version
python -m rlcoach.cli --help
python -m rlcoach.cli --version

# Ingest & validate a replay (prints file checks)
python -m rlcoach.cli ingest path/to/replay.replay

# Analyze a replay and write JSON (header‑only or with adapter)
python -m rlcoach.cli analyze path/to/replay.replay --header-only --out out --pretty

# Prefer the Rust adapter (if installed) for richer parsing
python -m rlcoach.cli analyze path/to/replay.replay --adapter rust --out out --pretty

# Generate JSON + Markdown dossiers
python -m rlcoach.cli report-md path/to/replay.replay --out out --pretty
python -m rlcoach.cli report-md path/to/replay.replay --adapter rust --out out --pretty

# View a generated report locally (pretty summary; optional per-player focus)
python -m rlcoach.ui view out/replay.json
python -m rlcoach.ui view out/replay.json --player "DisplayName"
```

### Features

- **Replay ingest**: Validates file bounds, surface CRC status, and captures deterministic file metadata.
- **Pluggable parsing**: Header-only fallback plus optional Rust bridge for network frames.
- **Normalization & events**: Builds a consolidated timeline and detects goals, demos, touches, challenges, boost pickups, and kickoffs.
- **14 Analysis modules**:
  - Core: fundamentals, boost economy, movement, positioning
  - Advanced: mechanics (jumps/flips/wavedashes), recovery quality, defense (shadow/last defender)
  - Metrics: expected goals (xG), ball prediction quality, passing, challenges, kickoffs
  - Visualization: heatmaps, rotation compliance, coaching insights
- **Reporting**: Emits schema-conformant JSON and a Markdown dossier with identical coverage.
- **Offline viewer**: `python -m rlcoach.ui` renders summaries without network dependencies.

## Sample Markdown Output

A complete dossier example is stored at `tests/goldens/synthetic_small.md`.

```markdown
## Team Metrics
| Metric | Blue | Blue Rate | Orange | Orange Rate | Delta Blue-Orange |
| Goals  | 0    | 0         | 0      | 0           | 0                 |
```

## Development

### Development Commands

```bash
# Run tests
make test

# Format code
make fmt

# Lint code  
make lint

# Regenerate the optional Rust adapter artifacts
make rust-dev

# Clean build artifacts
make clean

# Parser corpus health gate (JSON summary)
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
```

### Project Structure

- `src/rlcoach/` — Main package source code
- `tests/` — Test suite
- `schemas/` — JSON schema definitions
- `codex/Plans/` — Project planning and design documents
- `codex/tickets/` — Development work items
- `codex/logs/` — Engineering logs
- `codex/docs/` — Developer docs (e.g., parser adapter, UI)
- `parsers/rlreplay_rust/` — Optional Rust parser adapter (pyo3)

## Documentation

- [Implementation plan](codex/Plans/rlcoach_implementation_plan.md) — architecture and scope.
- [Markdown mapping](codex/docs/json-report-markdown-mapping.md) — JSON → Markdown coverage matrix.
- [Markdown composer plan](codex/docs/json-to-markdown-report-plan.md) — report generation roadmap.
- [Offline UI guide](codex/docs/ui.md) — CLI viewer usage.

## Architecture

The system follows a pipeline architecture:
- **Ingestion & Validation**: Process .replay files with integrity checks
- **Parser Layer**: Pluggable adapters extract header and network frame data
- **Normalization**: Converts raw data to standardized RLBot coordinate system
- **Events Detection**: Goals, demos, touches, challenges, boost pickups, kickoffs
- **Analysis Engine**: 14 independent analyzers with cached aggregation for performance
- **Report Generator**: Schema-conformant JSON reports + Markdown dossiers
- **Optional UI**: Local-only CLI interface for visualization

## Parsers & Adapters

- Available adapters
  - `null` (default) — header‑only fallback with explicit quality warnings
  - `rust` (optional) — pyo3 module that parses real headers and (when available) network frames
- Select an adapter at analysis time via `--adapter {rust,null}`.
- If the selected adapter is unavailable or fails, analysis falls back to `null`.

Build the Rust adapter locally (optional):

```bash
pip install maturin
cd parsers/rlreplay_rust
# Install into current env for development
maturin develop

# Or build a wheel and install it
maturin build -r
pip install target/wheels/*.whl
```

## Offline UI (CLI)

Render a concise summary of a generated report JSON:

```bash
python -m rlcoach.ui view out/replay.json
python -m rlcoach.ui view out/replay.json --player "DisplayName"
```

See `codex/docs/ui.md` for usage.

## License

MIT License - see LICENSE file for details.

## Contributing

Please see the implementation plan and tickets under `codex/` for current development status.
