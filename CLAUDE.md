# CLAUDE.md

This file provides guidance to Claude Code and other AI assistants when working with code in this repository.

## CRITICAL: Python Virtual Environment

**IMPORTANT: All Python commands MUST be run using the project's virtual environment.**

```bash
# ALWAYS activate venv before running Python commands:
source /Users/treygoff/Code/rlcoach/.venv/bin/activate

# Or prefix commands with the activation:
source .venv/bin/activate && python -m pytest
source .venv/bin/activate && python -m rlcoach.cli --help

# Common patterns that WILL FAIL without venv:
python -m pytest          # FAILS - no pytest installed globally
pytest tests/             # FAILS - command not found
python -m rlcoach.cli     # FAILS - missing dependencies
```

The virtual environment contains all required dependencies (pytest, black, ruff, maturin, etc.). System Python does NOT have these packages installed.

## Project Overview

rlcoach is an all-local Rocket League replay analysis tool for performance coaching. It processes .replay files locally and generates JSON reports + Markdown dossiers with player metrics, team analysis, and coaching insights.

## Pipeline Architecture

The system follows a strict pipeline: **ingest -> parse -> normalize -> events -> analyze -> report**

1. **Ingest** (`ingest.py`): Validates .replay files, computes SHA256, checks CRC
2. **Parser** (`parser/`): **Pluggable adapter pattern**—`null` (header-only fallback) or `rust` (full network frames via pyo3 + boxcars)
3. **Normalize** (`normalize.py`): Converts engine data to standardized timeline with RLBot field coordinates
4. **Events** (`events.py`): Detects goals, demos, touches, challenges, boost pickups, kickoffs
5. **Analysis** (`analysis/`): Independent modules with cached aggregation for performance
6. **Report** (`report.py`, `report_markdown.py`): Emits schema-conformant JSON + Markdown dossiers

**Key Design Principle**: **Degradation policy**—if network parsing fails, fall back to header-only mode with quality warnings. Analysis adapts to available data.

## Analysis Modules

The analysis layer (`src/rlcoach/analysis/`) contains these modules:

| Module | Purpose |
|--------|---------|
| `fundamentals.py` | Core stats (goals, assists, saves, shots) |
| `boost.py` | Boost economy, pickups, efficiency |
| `movement.py` | Speed, supersonic time, distance traveled |
| `positioning.py` | Field positioning, rotation compliance |
| `passing.py` | Pass detection and quality |
| `challenges.py` | 50/50s and challenge outcomes |
| `kickoffs.py` | Kickoff analysis |
| `heatmaps.py` | Position/touch density grids |
| `insights.py` | Player and team coaching insights |
| `mechanics.py` | Jump/flip/wavedash detection from physics |
| `recovery.py` | Landing quality and momentum retention |
| `defense.py` | Shadow defense, last defender tracking |
| `xg.py` | Expected goals model for shot quality |
| `ball_prediction.py` | Ball read quality analysis |

**Performance Note**: Expensive analyzers (mechanics, recovery, defense, ball_prediction, xg) are cached at the aggregator level in `__init__.py` to avoid redundant computation when iterating per-player.

## Parser Adapter Pattern

The parser layer uses pluggable adapters (`parser/interface.py`):
- **`null`** (`null_adapter.py`): Header-only fallback, always available
- **`rust`** (`rust_adapter.py`): Optional pyo3 module (`parsers/rlreplay_rust/`) for richer parsing
- Select at runtime via `--adapter {rust,null}` or `--header-only`
- If selected adapter fails, automatically falls back to `null`

## Development Structure

- `codex/Plans/` — Read `rlcoach_implementation_plan.md` before scope changes
- `src/rlcoach/` — Main package: `ingest.py`, `parser/`, `normalize.py`, `events.py`, `analysis/`, `report*.py`, `cli.py`, `ui.py`
- `tests/` — Pytest suite mirroring `src/` layout (261 tests)
- `schemas/` — JSON schema definitions (Draft-07)
- `parsers/rlreplay_rust/` — Optional Rust adapter (maturin build)

## Common Commands

```bash
# ALWAYS activate venv first!
source .venv/bin/activate

# First-time setup
make install-dev              # Install Black, Ruff, pytest, dev dependencies
make rust-dev                 # (Optional) Build Rust adapter with maturin

# Development workflow
make test                     # Run full pytest suite (PYTHONPATH=src pytest -q)
PYTHONPATH=src pytest tests/test_foo.py -q   # Run single test file
make fmt                      # Format with Black
make lint                     # Lint with Ruff
make clean                    # Clear build artifacts and caches

# CLI usage
python -m rlcoach.cli --help
python -m rlcoach.cli ingest path/to/replay.replay
python -m rlcoach.cli analyze path/to/replay.replay --adapter rust --out out --pretty
python -m rlcoach.cli report-md path/to/replay.replay --out out --pretty
python -m rlcoach.ui view out/replay.json
python -m rlcoach.ui view out/replay.json --player "DisplayName"
```

## Key Implementation Patterns

### Parser Adapter Selection
```python
# In report.py, adapters are tried in fallback order:
# 1. Try selected adapter (rust/null)
# 2. On failure, fall back to null adapter
# 3. Add quality warnings to report
```

### Analysis Module Independence
Each analyzer in `analysis/` is independent and stateless:
- Consumes normalized timeline from `normalize.py`
- Returns metrics dict with `per_player` and/or `per_team` keys
- Can gracefully degrade if data is missing
- Target >80% test coverage for analyzers

### Analysis Caching Pattern
```python
# In aggregate_analysis(), expensive analyzers are cached once:
cached_mechanics = analyze_mechanics(frames)
cached_defense = analyze_defense(frames)
# ... then results are extracted per-player from the cache
```

### Schema-Driven Development
- All reports validated against `schemas/*.json` (JSON Schema Draft-07)
- Schema version tracked in `schema_version` field
- Error reports follow `{"error": "...", "details": "..."}` structure

### Field Coordinates
Uses RLBot field constants (`field_constants.py`):
- Origin at center, side walls x=+-4096, back walls y=+-5120, ceiling z~2044
- Boost pad positions from RLBot reference
- `DEFAULT_FRAME_RATE = 30.0` constant for fallback frame rate

### Constants and Defaults
Key constants are centralized:
- `normalize.py`: `DEFAULT_FRAME_RATE`, `SUPERSONIC_*` thresholds
- `field_constants.py`: `FIELD`, `Vec3`, boost pad positions
- `physics_constants.py`: Ball/car physics values

## Testing Patterns

- Mirror `src/` structure in `tests/`
- Include both success and degraded scenarios (e.g., header-only fallback)
- Replay fixtures in `assets/replays/` (Git LFS for large files)
- Golden fixtures in `tests/goldens/*.json` and `*.md`
- Test builders in `tests/fixtures/builders.py` for synthetic frame data

## Codex Workflow

- `codex/Plans/rlcoach_implementation_plan.md` — architectural reference
- `codex/tickets/YYYY-MM-DD-title.md` — work items
- `codex/logs/YYYY-MM-DD-name.md` — engineering logs
- Link tickets in commits: `Relates-to: codex/tickets/2025-09-08-title.md`

## Recent Changes (November 2025)

- Fixed deprecated `datetime.utcnow()` -> `datetime.now(timezone.utc)`
- Added analysis caching to avoid redundant computation in aggregator
- Standardized API consistency (`per_team` key across all analyzers)
- Added `DEFAULT_FRAME_RATE` constant for consistent fallback values
- Removed deprecated placeholder functions from analysis module
- Fixed import consistency (Vec3 from field_constants)
- Fixed `third_man_pct` to return `None` for 2v2/1v1 matches (only meaningful in 3v3)
- Fixed xG module to only count SHOT outcomes (was incorrectly counting PASS touches)
- Fixed recovery momentum to cap at 100% for summary stats
- Fixed recovery detection thresholds to catch more recoveries in fast-paced play
- Fixed mechanics jump detection to count jumps that precede flips (jumps >= flips now)
