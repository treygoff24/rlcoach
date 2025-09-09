# rlcoach

All‑local Rocket League replay analysis tool for comprehensive performance coaching.

## Overview

rlcoach is designed to provide detailed analysis of Rocket League replays without requiring any cloud services or network connectivity. The tool processes .replay files locally and generates comprehensive JSON reports with player performance metrics, team analysis, and coaching insights.

## Project Status

- CLI, analyzers, and report generator are implemented with tests.
- Parser layer is pluggable:
  - "null" adapter (header‑only fallback; always available)
  - optional "rust" adapter (pyo3 + boxcars) for richer header parsing and network frames
- A minimal offline UI is available to view generated JSON reports.

See the [implementation plan](codex/Plans/rlcoach_implementation_plan.md) for scope and roadmap.

## Quick Start

### Installation

```bash
# Install development dependencies
make install-dev
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

# View a generated report locally (pretty summary; optional per‑player focus)
python -m rlcoach.ui view out/replay.json
python -m rlcoach.ui view out/replay.json --player "DisplayName"
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

# Clean build artifacts
make clean
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

## Architecture

The system follows a pipeline architecture:
- **Ingestion & Validation**: Process .replay files with integrity checks
- **Parser Layer**: Pluggable adapters extract header and network frame data
- **Analysis Engine**: Independent analyzers for fundamentals, boost economy, positioning, etc.
- **Report Generator**: Structured JSON reports per replay
- **Optional UI**: Local-only desktop interface for visualization

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

See `codex/docs/parser_adapter.md` for details.

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
