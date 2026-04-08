# User Testing

Testing surface findings, validation tools, and runtime guidance for validators.

**What belongs here:** validation surfaces, exact tools, setup expectations, concurrency guidance, and known gotchas.
**What does NOT belong here:** implementation plans or feature sequencing.

---

## Validation Surface

### Primary Surface: CLI analyze
Command pattern:
```bash
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out <dir> --pretty
```

Purpose:
- validates parser -> normalize -> events -> analysis -> JSON report
- verifies parser diagnostics/provenance and schema-valid report output

### Primary Surface: CLI report-md
Command pattern:
```bash
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --adapter rust --out <dir> --pretty
```

Purpose:
- validates paired JSON + Markdown generation
- verifies report/markdown parity and degraded/error handling

### Primary Surface: Corpus health
Command pattern:
```bash
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
```

Purpose:
- validates reliability floor, degraded accounting, usable parse rate, and final event/provenance coverage

### Secondary Surface: Rust build/test
Command patterns:
```bash
source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test
source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop
```

Purpose:
- validates Rust parser crate correctness and installability

### Secondary Surface: Automated Python tests
Representative commands:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q
source .venv/bin/activate && ruff check src/ tests/
source .venv/bin/activate && black --check src/ tests/
```

Purpose:
- validates parser-focused and full-suite regression safety

## Validation Concurrency

Machine profile observed during dry run:
- 16 logical CPUs
- 12 performance physical CPUs
- ~64 GiB RAM
- no active swap pressure observed

Observed workload cost:
- `maturin develop`: ~358 MB max RSS
- full `pytest -q`: ~418 MB max RSS
- corpus-health over 202 replays: ~299 MB max RSS and CPU-heavy

Recommended max concurrent validators for this mission:
- **CLI/test/corpus validation:** 4

Rationale:
- memory is not the limiting factor
- corpus-health and replay parsing are CPU-heavy sustained workloads
- 4 concurrent validators stays well inside 70% of practical CPU headroom while leaving room for the orchestrator and background processes

## Known Gotchas

- Always activate `.venv` before direct Python commands.
- Prefer direct `maturin develop` over `make rust-dev` if the latter trips on pip availability.
- Docker is unavailable and must not be part of the validation path.
- Existing unrelated local servers/ports are off-limits; this mission does not need them.
- Formatter state may already be dirty relative to `black --check`; validators should report it explicitly if still present.
