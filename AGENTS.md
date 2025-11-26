# Repository Guidelines for AI Agents

---

## CRITICAL: Python Virtual Environment

**YOU MUST USE THE VIRTUAL ENVIRONMENT FOR ALL PYTHON COMMANDS.**

This is the #1 cause of agent failures in this project. The system Python does NOT have pytest, black, ruff, or project dependencies installed.

### Required Pattern

```bash
# ALWAYS prefix Python commands with venv activation:
source /Users/treygoff/Code/rlcoach/.venv/bin/activate && <command>

# Examples:
source .venv/bin/activate && PYTHONPATH=src pytest -q
source .venv/bin/activate && python -m rlcoach.cli --help
source .venv/bin/activate && python -m pytest tests/test_foo.py
source .venv/bin/activate && python -c "from rlcoach.report import generate_report"
```

### Commands That WILL FAIL Without venv

```bash
# These ALL fail without venv activation:
python -m pytest                    # No module named pytest
pytest tests/                       # command not found: pytest
python -m rlcoach.cli              # ModuleNotFoundError
python3 -m pytest                   # No module named pytest
PYTHONPATH=src pytest              # command not found: pytest
```

### Why This Matters

- System Python (python3.14) has NO packages installed
- All dependencies live in `.venv/`
- The Makefile commands (`make test`) handle this automatically
- Direct Python/pytest invocations MUST activate venv first

---

## Project Structure & Module Organization

Core logic resides in `src/rlcoach`, grouped by ingest, parsing, events, analysis, and reporting stages; mirror any new module with a counterpart under `tests/`. The Rust replay bridge lives in `parsers/rlreplay_rust` and is compiled alongside Python bindings. Planning docs stay in `codex/Plans/`—always review `codex/Plans/rlcoach_implementation_plan.md` before proposing scope changes. Use `codex/docs/` for design notes, `codex/logs/` for session journals, and `codex/tickets/` (kebab-case filenames) for work items. Large fixture replays belong in `assets/replays/` and must go through Git LFS; JSON schemas reside in `schemas/`.

### Analysis Modules

The analysis layer (`src/rlcoach/analysis/`) contains 14 modules:

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

**Performance Pattern**: Expensive analyzers (mechanics, recovery, defense, ball_prediction, xg) are cached at the aggregator level in `__init__.py` to avoid redundant computation.

---

## Build, Test, and Development Commands

```bash
# ALWAYS activate venv first!
source .venv/bin/activate

# First-time setup
make install-dev              # Install Black, Ruff, pytest, dev dependencies
make rust-dev                 # (Optional) Build Rust adapter with maturin

# Running tests (261 tests, ~8 seconds)
source .venv/bin/activate && PYTHONPATH=src pytest -q           # Full suite
source .venv/bin/activate && PYTHONPATH=src pytest tests/test_foo.py -q  # Single file
make test                     # Alternative (handles venv internally)

# Code quality
make fmt                      # Format with Black
make lint                     # Lint with Ruff
make clean                    # Clear build artifacts
```

---

## Markdown Report Generation

Use `python -m rlcoach.cli report-md path/to/replay.replay --out out --pretty` to produce both the JSON schema payload and the Markdown dossier in one call. The command writes `<stem>.json` and `<stem>.md` atomically; the Markdown composer can still emit an error summary when parsing fails. Golden fixtures under `tests/goldens/*.md` illustrate the expected table layout.

---

## Coding Style & Patterns

### General Style
- Python code follows Black (88 columns) and Ruff defaults
- Prefer compact, pure functions and explicit return types
- Modules, functions, variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`

### Import Conventions
- Use `from ..field_constants import Vec3` (not `parser.types.Vec3`)
- Use `from ..normalize import DEFAULT_FRAME_RATE` for frame rate constant
- Use `datetime.now(timezone.utc)` (not deprecated `utcnow()`)

### Analysis Module API
All analyzers must return dicts with consistent keys:
```python
return {
    "per_player": {...},  # Keyed by player_id
    "per_team": {...},    # "blue" and "orange" keys
}
```

### Analysis Caching Pattern
```python
# In aggregate_analysis(), expensive analyzers are cached once:
cached_mechanics = analyze_mechanics(frames)
cached_defense = analyze_defense(frames)
# ... then results are extracted per-player from the cache
```

---

## Testing Guidelines

All tests run under pytest; name files `test_*.py` mirroring the `src/` tree. Provide both successful and degraded scenarios (e.g., header-only fallback) for new analyzers or ingest paths. Maintain >=80% coverage for analyzers and schema validators. Use `tests/fixtures/builders.py` for synthetic frame data and store shared replay fixtures in `assets/replays/`.

---

## Commit & Pull Request Guidelines

Use Conventional Commits such as `feat(parser): add kickoff outcomes`. Keep each PR focused, document rationale and before/after JSON snippets, and link tickets with `Relates-to: codex/tickets/yyyy-mm-dd-title.md`. Update related docs and schemas alongside code, and include `make test` results in the PR description.

---

## Security & Agent Notes

Analysis stays fully local—avoid remote calls in parsers or analyzers. Do not commit raw ladder replays; reference Git LFS pointers instead. Codex CLI agents must log progress in `codex/logs/`, refresh the active plan if scope shifts, and prefer targeted tests over broad refactors to match repository expectations.

---

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
