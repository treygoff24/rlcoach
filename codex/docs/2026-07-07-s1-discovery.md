# S1.0 Discovery: rlinput Workspace, RocketSim, Meshes, Physics Buckets

Date: 2026-07-07
Branch: `feat/s1-discovery`
Scope: discovery/build skeleton only. No solver, estimator, or `InputTimeline` design is included.

## Executive decision

- Use a root Cargo workspace with `parsers/rlreplay_rust` and new `parsers/rlinput` members.
- Pin `rocketsim_rs = "=0.37.0"` behind the `rlinput/sim` feature.
- Do not commit Rocket League collision meshes. Treat full RocketSim standard-arena runs as local/manual until a legally reviewed fetch/dump workflow exists; keep CI on feature-gated `TheVoid` API proof plus the future simplified air-phase objective.
- Segment V1 metrics by replay build bucket. The current corpus has three buckets, all after Rocket League v2.53's published CPU-architecture physics correction.

## Workspace layout

Decision: root workspace.

Why:

1. Repo-level `cargo test` / `cargo clippy` now work from the same root where Python gates run.
2. The existing parser can remain at `parsers/rlreplay_rust` for `maturin` and CI path stability.
3. `rlinput` can live beside parser crates without implying Python package ownership.
4. The root workspace can own one authoritative `Cargo.lock` while keeping `rlreplay_rust` dependency-light.

Implementation notes:

- Added root `Cargo.toml` with workspace members:
  - `parsers/rlreplay_rust`
  - `parsers/rlinput`
- Moved the macOS PyO3 linker config from `parsers/rlreplay_rust/.cargo/config.toml` to root `.cargo/config.toml`; otherwise root `cargo test` fails linking the Python extension crate on macOS.
- Removed the member-level `parsers/rlreplay_rust/Cargo.lock`; root `Cargo.lock` is now authoritative.
- Pinned `boxcars` in `rlreplay_rust` to `=0.10.7` so the workspace lock does not silently float the existing parser to newer `boxcars` behavior.
- CI change made: `.github/workflows/ci.yml` now caches Rust workspace `.` and installs the parser wheel from `../../target/wheels/*.whl` because `maturin build` invoked from a workspace member writes to the root target directory.

## `rlinput` skeleton and RocketSim feature gate

Added `parsers/rlinput` as a library crate only:

- default feature set: empty
- `sim` feature: enables optional `rocketsim_rs`
- no estimator or solver logic

Compile-time/runtime proof:

- `cargo test -p rlinput --features sim`
- The test initializes RocketSim from memory with no meshes, creates a `GameMode::TheVoid` arena at 120 Hz, adds an Octane, sets full car state (`position`, rotation matrix, linear velocity, angular velocity, boost/contact fields), applies controller inputs, steps eight ticks, and reads state back.

Important limitation: this proves the Rust wrapper API and per-tick stepping path. It does not prove standard Soccar collision behavior because no collision mesh dump is available locally and this task intentionally does not commit mesh binaries.

## RocketSim pin and API verification

Pinned Rust crate:

- crate: `rocketsim_rs`
- version: `=0.37.0`
- license reported by crates.io metadata: MIT
- wrapper repository: `https://github.com/VirxEC/rocketsim-rs`
- published crate VCS commit from `.cargo_vcs_info.json`: `c7623a1155b452a99667c45b823d1bc0fd41f397`
- vendored RocketSim submodule revision in that repo: `f80f9d90f922315c5877a81987845d3242ff1780`
- RocketSim tag at that revision: `v2.2.1`

Verified API surface from local compile/run and crate source:

- initialization:
  - `rocketsim_rs::init(collision_meshes_folder: Option<&str>, silent: bool)`
  - `rocketsim_rs::init_from_mem(soccar: &[&[u8]], hoops: &[&[u8]])`
- arena creation:
  - `Arena::new(GameMode, ArenaConfig, tick_rate)`
  - `Arena::default_standard()` for standard Soccar at 120 Hz
- car control/state:
  - `add_car(Team, CarConfig::octane())`
  - `set_car(car_id, CarState)`
  - `set_car_controls(car_id, CarControls)`
  - `step(tick_count)`
  - `get_car(car_id)`
  - `get_tick_rate()` / `get_tick_count()`

The local proof compiled and ran with `GameMode::TheVoid` because that path does not require mesh assets.

## RocketSim physics patch target

The pinned `rocketsim_rs 0.37.0` vendors RocketSim `v2.2.1` (`f80f9d90`, released 2026-04-19). The v2.2.1 release is a smaller fix release on top of v2.2. Reported fixes include Dropshot/Heatseeker mesh access, `MutatorConfig` compatibility, Dropshot respawn locations, merged meshes for all game modes, and flip-torque scaling with tick time.

RocketSim does not publish an exact `BuildVersion`/`Changelist` compatibility matrix for Rocket League replay headers. The best decision-grade statement for S1.2 is therefore:

- It is the latest stable Rust wrapper available from crates.io at discovery time.
- It targets RocketSim v2.2.1 physics behavior, not a specific replay `BuildVersion` string.
- The current corpus starts after the official Rocket League v2.53 CPU-architecture physics correction (2025-06-17).
- I found no official standard-Soccar physics changes in the visible v2.59, v2.60, or v2.63 patch notes that cover the sampled replay dates, but LTMs and mutator/private-match settings can still invalidate standard-physics assumptions.

Recommendation: use the bucket table below for V1 metric segmentation and keep a standard-playlist/mutator filter in scope before interpreting RocketSim residuals.

## Collision mesh discovery

RocketSim standard arenas require Rocket League collision meshes at initialization.

Known sources:

1. Official RocketSim dumper: `ZealanL/RLArenaCollisionDumper`
   - License: MIT for dumper code.
   - Platform/flow: Windows, Rocket League running; scans live process memory and dumps `./collision-meshes/`.
   - Expected mesh counts in source: Soccar 16, Hoops 12, Dropshot 2.
   - Release asset is the dumper executable, not mesh data.
2. Rust dumper: `VirxEC/rl_arena_collision_dumper`
   - License: MIT for dumper code.
   - Platform/flow: Windows/Linux, game closed; requires `umodel` and a local Rocket League `TAGame/CookedPCConsole` path.
   - Covers Soccar/Hoops in the inspected source; less complete than the official dumper for current RocketSim game modes.
3. `rocketsim_rs` examples can embed `collision_meshes/soccar/*.cmf`, but the example source explicitly says not to redistribute mesh files.

Local measurement status:

- No Rocket League install was found under the local Steam common directory.
- No local `TAGame` path or `collision_meshes` dump was found in the repo/cargo-searchable locations inspected.
- Because no mesh dump exists on this host, I could not honestly measure the final mesh directory size. The binary dumper release sizes are small, but they are not the mesh payload.

Licensing/CI recommendation:

- Do not commit mesh binaries in Git or LFS without legal review. They are derived from Rocket League assets even if the dumper code is MIT.
- Do not make CI depend on full standard RocketSim meshes.
- Keep CI on:
  - `cargo test -p rlinput --features sim` using `GameMode::TheVoid`
  - later simplified air-phase integrator tests
- Add a future local-only helper such as `RLCOACH_ROCKETSIM_MESH_DIR=/path/to/collision_meshes` once S1.2 needs full Soccar verification.

One-line recommendation: no mesh binaries in-repo; local/manual full-sim only, CI uses meshless proof plus simplified air-phase tests.

## Replay build bucket scan

Command:

```bash
source .venv/bin/activate && python scripts/scan_replay_builds.py
```

Result: 202 replay files scanned, 202 ok, 0 errors.

| BuildVersion | BuildID | Changelist | GameVersion | Count | Sources | Date span | RecordFPS | Top maps | Compatibility |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| 250811.43331.492665 | 151471783 | 492665 | 30 | 5 | `Replay_files` x5 | 2025-09-07 23-50-01 -> 2025-09-12 20-01-41 | 30.0 x5 | CHN_Stadium_P x1, Wasteland_GRS_P x1, Outlaw_Oasis_P x1 | RocketSim v2.2.1 / `rocketsim_rs 0.37.0`: probable standard-physics match; segment V1 metrics by this bucket |
| 250909.54128.495700 | -1459478734 | 495700 | 30 | 1 | `Replay_files` x1 | 2025-09-25 14-33-19 -> 2025-09-25 14-33-19 | 30.0 x1 | UtopiaStadium_P x1 | RocketSim v2.2.1 / `rocketsim_rs 0.37.0`: probable standard-physics match; segment V1 metrics by this bucket |
| 251202.62834.504897 | -680142666 | 504897 | 30 | 196 | `replays` x196 | 2025-12-23 22-27-17 -> 2026-01-01 12-40-11 | 30.0 x196 | Paname_Dusk_P x29, mall_day_p x11, cs_day_p x9 | RocketSim v2.2.1 / `rocketsim_rs 0.37.0`: probable standard-physics match; segment V1 metrics by this bucket |

Script location: `scripts/scan_replay_builds.py`.

## Verification performed

Final local verification was green:

```bash
source .venv/bin/activate && ruff check src/ tests/
source .venv/bin/activate && black --check src/ tests/
source .venv/bin/activate && PYTHONPATH=src pytest -q
cargo test
cargo clippy --all-targets
cargo test -p rlinput --features sim
cargo clippy --all-targets --all-features
make rust-dev
```

Additional CI-style wheel path verification was green:

```bash
source .venv/bin/activate
cd parsers/rlreplay_rust
python -m maturin build --release
pip install ../../target/wheels/*.whl
python -c "import rlreplay_rust as m; print(getattr(m, 'RUST_CORE', False))"
```

## Risks for S1.2

1. Biggest risk: full standard-arena RocketSim validation is blocked on collision meshes whose licensing and CI distribution path are not settled.
2. RocketSim's release/tag history does not provide an exact replay `BuildVersion` compatibility matrix, so drift detection must be empirical and bucketed.
3. The current proof uses `GameMode::TheVoid`; Soccar collision/ground-contact behavior still needs a local mesh-backed smoke test before solver scoring relies on it.
4. Replay buckets do not by themselves prove standard physics. LTM, mutator, and private-match settings can still contaminate residual metrics.
5. The parser crate now shares a root Cargo lockfile; future dependency updates must avoid accidental parser behavior drift.
