# 0925 Replay Parity Plan

## Latest Replay Run
- Executed `python -m rlcoach.cli report-md Replay_files/0925.replay --out out --pretty`; refreshed `out/0925.json` and `out/0925.md` successfully.
- Output currently validates against our schema but diverges materially from Ballchasing’s published metrics for the same replay.

## Key Gaps vs Ballchasing
- **Movement buckets**: `movement.avg_speed_kph` and speed buckets stay in the 90–106 kph range while Ballchasing reports ~1 600 uu/s and 50–120 s of supersonic time; our supersonic flag never triggers.
- **Boost economy**: Collection totals differ by 70–140 boost, stolen counts are inflated by 166–519 boost, and time spent at 0/100 boost runs 9–29 s higher than Ballchasing.
- **Powerslides & aerials**: Detectors barely register (0–2 powerslides vs Ballchasing’s 25–54; aerial time also under-reported) indicating missing angular velocity and airtime handling.
- **Kickoff analytics**: No first-possession wins, `avg_time_to_first_touch_s` ≈ 0.05 s, and approach types skew toward “STANDARD”, despite Ballchasing reporting realistic outcomes.
- **Identity handling**: We lose fidelity on names/IDs (`Skillz. †` vs `Skillz.`) which hampers direct joins with external data.

## Remediation Roadmap
1. **Parity Harness**: Add `tests/analysis/test_ballchasing_parity.py` (and fixtures) to ingest all five `Replay_files/*.replay`, load the paired Ballchasing CSVs, and assert tolerances on per-player/per-team fundamentals, boost, movement, positioning, and kickoffs. Serialize the current comparison script into reusable helpers so future regressions fail fast.
2. **Player Identity Plumbing**: Update `src/rlcoach/report.py` to prefer stable platform IDs (`platform:entity` composite), keep sanitized display-name slugs, and surface both forms so JSON, Markdown, and parity tests join reliably.
3. **Movement Analytics**: In `src/rlcoach/analysis/movement.py`, operate in uu/s (retain kph for presentation), realign bucket thresholds to Ballchasing’s definitions, accumulate time via exact frame `dt`, and overhaul aerial/powerslide detection to use true angular velocity and altitude derived from frames rather than yaw deltas.
4. **Boost Tracking**: Rework boost pickup detection in `src/rlcoach/events.py` and aggregation in `src/rlcoach/analysis/boost.py` to derive pad identity from frame actors, compute pre/post boost from consecutive frames, classify “stolen” based on pad location relative to the attacking team, and recalculate BCPM using consistent definitions (boost units/min). Align zero/100 thresholds with Ballchasing (≤3 boost, ≥99 boost) and reconcile waste heuristics.
5. **Kickoff & Touch Logic**: Tighten kickoff/touch handling so we detect first possession via post-kickoff control streaks, record kickoff goals, calculate realistic time-to-first-touch using kickoff frame rate, and classify approach types using movement vectors/flip detection rather than heuristics alone.
6. **Positioning & Passing Alignment**: Review `src/rlcoach/analysis/positioning.py` and `src/rlcoach/analysis/passing.py` so thirds/halves totals, possession windows, and turnover counts line up with Ballchasing outputs; document calibrated thresholds in `codex/docs/`.
7. **Golden Outputs & Docs**: Regenerate Markdown/JSON goldens under `tests/goldens/`, update developer docs with calibrated metric definitions, and lock the parity harness into CI.

## Immediate Next Steps
- Implement each remediation tranche in order, running the parity pytest plus `make test` after every major change.
- Once metrics align for all local replays, regenerate `out/*.md` dossiers and capture manual validation notes/screenshots.

## External Reference: python-ballchasing Insights
- The open-source [`python-ballchasing`](https://github.com/Rolv-Arild/python-ballchasing) project enumerates every Ballchasing stat in `ballchasing/stats_info.tsv`; we can reuse that mapping to verify field names, team/player applicability, and data types when comparing outputs.
- Their `ballchasing/util.py::parse_replay_stats` routine flattens API payloads into replay/team/player dictionaries using stable player IDs composed of `{platform}:{id}`, a pattern we should mirror for deterministic joins.
- The `ballchasing/constants.py` and `ballchasing/typed/*` modules capture canonical playlist/rank/map enums and typed response structures. These files provide authoritative source data for validation tables, schema enums, and doc cross-links when we align our output with Ballchasing terminology.
