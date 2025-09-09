**Rust Parser Adapter (pyo3) — Build & Usage**

- Goal: Provide a local Rust core that exposes minimal `parse_header(path)` and `iter_frames(path)` via a Python module using `pyo3`.
- Scope: Header fields are placeholders but deterministic; frames iterator is a stub. This is a foundation for future full parsing.

**Layout**
- `parsers/rlreplay_rust/` — Rust crate compiled as a Python extension.
- Python shim: `src/rlcoach/parser/rust_adapter.py` implements the `ParserAdapter` interface and gracefully degrades if the Rust core is unavailable.

**Prereqs**
- Rust toolchain: `rustup` with a stable toolchain.
- Python dev headers.
- Optional: `maturin` for building/installing wheels.

Commands
- Build (debug): `cd parsers/rlreplay_rust && cargo build`
- Build (release): `cd parsers/rlreplay_rust && cargo build --release`
- Build wheel (recommended):
  - `pip install maturin`
  - `cd parsers/rlreplay_rust`
  - `maturin develop` (installs into the current virtualenv)

**Using the Adapter**
- In Python: `from rlcoach.parser import get_adapter; adapter = get_adapter('rust')`
- Header parse: `adapter.parse_header(Path('testing_replay.replay'))`
- Network frames: `adapter.parse_network(Path('testing_replay.replay'))` returns a valid stub structure if the Rust core is present, or `None` otherwise.

**Degradation Behavior**
- If the Rust module `rlreplay_rust` is not importable, the adapter falls back to header-only mode using the ingest validator and adds clear quality warnings:
  - `rust_core_unavailable_fallback_header_only`
  - `network_data_unparsed_fallback_header_only`

**Notes**
- The Rust implementation here is a stub that detects replay “shape” by scanning the first 2KB for known markers (e.g., `TAGame.Replay_`). It returns deterministic placeholder values and is safe/offline.
- Future work: integrate `boxcars`/`rrrocket` to populate real header and frame data.

