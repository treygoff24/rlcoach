# Boost Pad Ground Truth – 2025-10-20

## Reproduction
- Ensure Rust toolchain + Python deps installed (`source ~/.cargo/env`, `export PATH="$HOME/Library/Python/3.9/bin:$PATH"`, `pip install --user -e ".[dev]"`).
- Build and install the Rust bridge (`cd parsers/rlreplay_rust && maturin build --release`, then `pip install --user target/wheels/rlreplay_rust-0.1.0-cp38-abi3-macosx_11_0_arm64.whl`).
- Collect telemetry (first 500 frames) with `python3 scripts/collect_boost_telemetry.py <replay> --max-frames 500 --frames --pretty --out codex/logs/<slug>.json`.
- Summarise with `python3 -m scripts.boost_parity_summary codex/logs/<slug>.json`.
- Optional: raw frames via `cargo run --example debug_first_frames -- <replay> --max-frames 500 --pretty > out.json`.

## Standard Soccar – Champions Field (`codex/logs/2025-10-20-boost-telemetry-champions-field.json`)
- Map `cs_day_p`, engine build `250811.43331.492665`, 500 frames sampled.
- Totals: 69 boost events (42 `pickup_new`, 27 `trajectory`); 16 pad actors observed within window.
- State mix: 25 `COLLECTED`, 17 `RESPAWNED`.
- Instigator coverage: 25/25 resolved events, **44 events missing `instigator_actor_id`** (respawns broadcast without owner).
- Pad coverage gap: only 16/34 pads emitted trajectory in first 500 frames → extend sampling window when auditing full matches.

## Variant Arena – Wasteland (`codex/logs/2025-10-20-boost-telemetry-wasteland.json`)
- Map `Wasteland_GRS_P`, same engine build, 500-frame slice.
- Totals: 75 boost events (44 `pickup_new`, 31 `trajectory`); 18 pad actors surfaced.
- State mix: 25 `COLLECTED`, 19 `RESPAWNED`; 50 events lack `instigator_actor_id`.
- Alt layout highlights: wall pads (actors 61–65) present but never tie to players—Ballchasing attribution will exceed ours until we resolve owner chain for these components.

## Older Engine – Neo Tokyo (`codex/logs/2025-10-20-boost-telemetry-neo-tokyo.json`)
- Map `CHN_Stadium_P`, engine build `250811.43331.492665` (pre-September patch), 500 frames.
- Totals: 198 boost events (121 `pickup_new`, 77 `trajectory`); 30 pad actors seen.
- State mix: 58 `COLLECTED`, 63 `RESPAWNED`, none marked `UNKNOWN`.
- Instigator coverage: only 58/198 events resolve to a car; **140 events broadcast without instigator** on older build—primary parity gap versus Ballchasing.
- Notable: high-frequency respawns without owners suggest we must hook `Attribute::Pickup` or follow component owner chain further when `PickupNew.instigator == None`.

## Parity Notes & Follow-ups
- Ballchasing fixtures (e.g., `tests/fixtures/boost_parity/0925_ballchasing_players.json`) report per-player pickup counts; our telemetry still drops 44–140 instigator links per replay, preventing apples-to-apples deltas.
- Need additional instrumentation:
  1. Capture `Attribute::Pickup` alongside `PickupNew` to detect pad recoveries with raw states `255`/`0`.
  2. Emit component-owner chain for `Pickup` actors when `instigator` is `None` (most respawns today).
  3. Expand sampling beyond 500 frames or emit once-per-pad canonical trajectory to guarantee full 34-pad coverage.
- Once owner resolution is complete, re-run `scripts/diff_boost_parity.py --rlcoach-json <report> --ballchasing-json tests/fixtures/boost_parity/0925_ballchasing_players.json` to quantify numeric parity.
