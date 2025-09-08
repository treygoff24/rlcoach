# rlcoach

All-local Rocket League replay analysis tool for comprehensive performance coaching.

## Overview

rlcoach is designed to provide detailed analysis of Rocket League replays without requiring any cloud services or network connectivity. The tool processes .replay files locally and generates comprehensive JSON reports with player performance metrics, team analysis, and coaching insights.

## Project Status

**Early Development** - This project is currently in the planning and scaffolding phase. See the [implementation plan](codex/Plans/rlcoach_implementation_plan.md) for the complete project roadmap.

## Quick Start

### Installation

```bash
# Install development dependencies
make install-dev
```

### Usage

```bash
# Run the CLI (currently a stub)
python -m rlcoach.cli --help
python -m rlcoach.cli --version
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
- `schemas/` — JSON schema definitions (future)
- `codex/Plans/` — Project planning and design documents
- `codex/tickets/` — Development work items
- `codex/logs/` — Engineering logs

## Architecture

The planned system follows a pipeline architecture:
- **Ingestion & Validation**: Process .replay files with integrity checks
- **Parser Layer**: Pluggable adapters extract header and network frame data
- **Analysis Engine**: Independent analyzers for fundamentals, boost economy, positioning, etc.
- **Report Generator**: Structured JSON reports per replay
- **Optional UI**: Local-only desktop interface for visualization

## License

MIT License - see LICENSE file for details.

## Contributing

This project is in early development. Please see the implementation plan and ticket system in the `codex/` directory for current development status.