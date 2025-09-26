# Boost Economy Calibration Follow-up

## Context
- `src/rlcoach/normalize.py` now zero-bases the replay timeline and trims post-match frames; `src/rlcoach/report.py` reads the normalized duration.
- Boost pickup detection (`src/rlcoach/events.py`) still overstates stolen pads and total collected boost when compared to Ballchasing reference CSVs under `Replay_files/ballchasing_output/` (e.g., Blue team 1537 stolen vs. 813 expected).
- Latest report regenerated via `python -m rlcoach.cli report-md Replay_files/0925.replay --out out --pretty` with duration 304.88 s and misaligned boost metrics.

## Goals
1. Bring team/player boost totals (amount_collected/stolen, pad counts) within 2-3% of Ballchasing baselines for replay `Replay_files/0925.replay`.
2. Preserve existing pickup telemetry fields (`boost_before/after/gain`, stolen flag) for analyzers that already depend on them.

## Next Steps
1. **Pad Availability Gating**
   - Instrument `detect_boost_pickups` to track `pad_last_pickup_time` (per `pad_id`).
   - Reject candidates that respawn too quickly (10 s for big pads, 4 s for small pads). Account for merge-window reuse when players linger on pads.
2. **Big vs Small Pad Attribution**
   - Use boost gain heuristics alongside proximity to disambiguate small vs. big pads when velocities/increments blur (e.g., 70+ boost gains from centers).
   - Consider checking historical `player.position` just before the pickup (e.g., 2-3 frames back) for better pad matching.
3. **Telemetry Validation Script**
   - Write a helper (`codex/scripts` or ad-hoc notebook) that cross-tabulates detected pickups vs. Ballchasing CSV totals to quickly flag mismatches while iterating.
4. **Regression Coverage**
   - Once metrics align, add assertions into `tests/test_analysis_boost.py` or a new fixture test to lock in expected totals for the 0925 replay.
5. **Report Regeneration**
   - Re-run `python -m rlcoach.cli report-md Replay_files/0925.replay --out out --pretty` and capture diffs against the Ballchasing CSV to document improvements in the PR.
