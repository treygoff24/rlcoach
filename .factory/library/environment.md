# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** required tools, local replay corpus assumptions, Rust/Python environment constraints, and known setup caveats.
**What does NOT belong here:** service commands or ports (use `.factory/services.yaml`).

---

## Required Local Tooling

- Python virtual environment at `.venv`
- Rust toolchain (`cargo`, `rustc`)
- `maturin` available inside the venv
- Local replay fixtures/corpus under `Replay_files/` and `replays/`

## Required Command Pattern

All direct Python commands must use the project virtualenv:

```bash
source .venv/bin/activate && <command>
```

## Mission-Specific Setup Notes

- Parser validation is local-only; no external API credentials are required.
- Docker is not available for this mission and should not be assumed.
- Direct `maturin develop` works for building the Rust parser extension.
- The convenience path `make rust-dev` may be brittle because `.venv/bin/python -m pip` is not currently reliable in this environment.

## Replay Corpus Notes

Validation relies on the local replay corpus already present in this workspace:
- `testing_replay.replay`
- `Replay_files/`
- `replays/`

Corpus-health assertions should be validated against the existing local corpus rather than a committed fixture bundle.
