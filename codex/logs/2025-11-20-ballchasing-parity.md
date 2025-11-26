# 2025-11-20 - Ballchasing parity closed on 0925 fixture

## What I did
- Activated venv, installed local wheel for `rlreplay_rust`, and regenerated `out/0925.json`/`out/0925.md`.
- Wired fundamentals to header stats using canonical player IDs (steam-prefixed) so per-player goals/assists/shots/saves/score match the scoreboard.
- Adjusted team boost aggregation to sum per-player averages (to mirror Ballchasing team CSV) and left other boost sums intact.
- Rebuilt goal detection to rely on header goal frames and identity maps; trimmed fallback path; tightened shot detection heuristics to reduce inflated touch/shot spam.
- Flipped the Ballchasing parity test from xfail to a real assertion; the 0925 snapshot now passes with zero deltas.

## Commands
- `.venv/bin/python -m rlcoach.cli report-md Replay_files/0925.replay --out out --pretty`
- `.venv/bin/pytest tests/analysis/test_ballchasing_parity.py -q`
