**Rust Parser Adapter (pyo3) — Build & Usage**

- Goal: Provide a local Rust core (boxcars-backed) that exposes `parse_header(path)` and `iter_frames(path)` via a Python module using `pyo3`.
- Scope: Header parsing uses real replay properties; `iter_frames` emits network frames with ball and player states when available. If the Rust core is unavailable, the adapter degrades to a header-only path with explicit quality warnings.

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
- Network frames: `adapter.parse_network(Path('testing_replay.replay'))` returns `NetworkFrames` with a list of dict frames when the Rust core is present; otherwise `None` (falls back to header-only analysis).

- **Degradation Behavior**
- If the Rust module `rlreplay_rust` is not importable, the adapter falls back to header-only mode using the ingest validator and adds clear quality warnings:
  - `rust_core_unavailable_fallback_header_only`
  - `network_data_unparsed_fallback_header_only`

**Frame Schema (emitted by iter_frames)**
- Frame dict keys: `timestamp`, `ball`, `players`
- `ball`: `{ position: {x,y,z}, velocity: {x,y,z}, angular_velocity: {x,y,z} }`
- Each entry in `players` includes: `{ player_id: str, team: int, position: {x,y,z}, velocity: {x,y,z}, rotation: {x,y,z}, boost_amount: int, is_supersonic: bool, is_on_ground: bool, is_demolished: bool }`

**Debugging Network Frames**
- The module exposes `debug_first_frames(path: str, max_frames: int)` to inspect the actor classes and attribute kinds for the first N frames. This helps verify actor classification (ball vs car) and attribute coverage on new replays/builds.

**Notes**
- The Rust implementation uses `boxcars` to read header and network frames. On some replays/builds, certain attributes may differ; the adapter includes conservative fallbacks and can be extended in a table-driven way as needed.
