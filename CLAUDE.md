# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
rlcoach is an all-local Rocket League replay analysis tool designed for comprehensive performance coaching. The project implements a modular architecture that ingests .replay files, parses them locally, and generates detailed JSON reports with player performance metrics, team analysis, and coaching insights.

## Architecture
The system follows a pipeline architecture:
- **Ingestion & Validation**: Accepts .replay files with integrity checks and CRC metadata
- **Parser Layer**: Pluggable adapters (`null` header-only fallback and optional Rust adapter) extract header and network frame data
- **Normalization Layer**: Converts engine data to standardized timelines and merged actor state
- **Analysis Engine**: Independent analyzers for fundamentals, boost economy, positioning, passing, movement, challenges, kickoffs, rotation compliance, and heatmaps
- **Report Generator**: Outputs structured JSON plus Markdown dossiers per replay
- **Optional UI**: Local-only CLI viewer renders summaries from generated JSON

## Key Design Principles
- **All-local processing**: No cloud APIs or network calls in core analyzers
- **Degradation policy**: Header-only fallback when network data fails
- **Community metric alignment**: Consistent with Ballchasing and established RL analytics
- **Schema versioning**: Formal JSON Schema with version tracking

## Development Structure
- `codex/Plans/` — Single source of truth for project scope. Read `rlcoach_implementation_plan.md` first
- `codex/docs/` — Design documentation and workflow guides  
- `codex/tickets/` — Work items created from `TICKET_TEMPLATE.md`
- `codex/logs/` — Engineering logs using `LOG_TEMPLATE.md`
- `src/` — rlcoach Python package (ingest, parser adapters, normalization, events, analysis, reporting, CLI/UI)
- `tests/` — Pytest suite mirroring the `src/` layout
- `schemas/` — JSON schema definitions
- `parsers/rlreplay_rust/` — Optional Rust network parser built with maturin

## Common Commands

```bash
# Install development dependencies (Black, Ruff, pytest, maturin helpers)
make install-dev

# Run formatting and linting
make fmt
make lint

# Execute the full test suite (pytest -q)
make test

# Build the optional Rust replay adapter
make rust-dev

# Generate reports from a replay
python -m rlcoach.cli analyze path/to/file.replay --out out --pretty
python -m rlcoach.cli report-md path/to/file.replay --out out --pretty

# View a generated JSON dossier in the terminal
python -m rlcoach.ui view out/example.json
```

**Create new ticket:**
```bash
cp codex/tickets/TICKET_TEMPLATE.md codex/tickets/2025-MM-DD-short-title.md
```

**Start engineering log:**
```bash
cp codex/logs/LOG_TEMPLATE.md codex/logs/2025-MM-DD-yourname.md
```

## File Conventions
- **Filenames**: kebab-case for Markdown/docs, date-prefixed for tickets/logs
- **JSON**: 2-space indent, snake_case keys, deterministic field order
- **Code**: modules `snake_case`, types `PascalCase`, functions `snake_case`

## Testing Strategy
- Co-locate tests under `tests/` mirroring module paths
- Target >80% coverage for analyzers and schema validators  
- Store replay samples under `assets/replays/` (use Git LFS for large files)
- Include both happy path and degraded/fallback test cases

## Commit Guidelines
- Use Conventional Commits: `feat(parser): add header-only fallback`
- Link tickets: `Relates-to: codex/tickets/2025-09-08-add-replay-parser.md`
- Update docs/schemas alongside code changes

## Analysis Modules
The system implements comprehensive analysis across multiple dimensions:

**Fundamentals**: Goals, assists, shots, saves, demos, shooting percentage
**Boost Economy**: BPM/BCPM, stolen pads, overfill/waste tracking, time at 0/100%
**Movement**: Speed brackets, ground/air time, aerials, powerslides  
**Positioning**: Field occupancy (halves/thirds), ball relationship, role detection
**Passing**: Possession chains, pass completion, turnovers, give-and-go sequences
**Challenges**: 50/50 outcomes, first-to-ball rate, risk assessment
**Kickoffs**: Approach classification, coordination analysis, outcome tracking

## JSON Schema
The system outputs structured reports following a formal JSON Schema (Draft-07) with:
- Replay metadata and quality warnings
- Per-team and per-player metrics
- Event timeline with frame-accurate data
- Coaching insights with evidence backing
- Error handling with standardized error objects

## Performance Considerations
- Zero-copy parsing where possible
- Parallel analyzer execution
- Chunked frame iteration for large replays
- Coordinate system based on RLBot field constants
- Frame rate disclosure (typically ~30 FPS from 120 Hz physics)

## Security Notes
- Designed for all-local operation
- No network calls in core analyzers
- Avoid committing large or sensitive replay files
- Use proper file validation and integrity checks
