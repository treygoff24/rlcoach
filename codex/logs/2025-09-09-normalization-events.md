# 2025-09-09 — Normalization & Events Calibration

Relates-to: codex/tickets/2025-09-09-normalization-and-events-calibration.md
Plan: codex/Plans/rlcoach_implementation_plan.md

Summary
- Verified ingestion path for Rust-shaped frame dicts in normalization.
- Fixed boost amount extraction for dict frames (`boost_amount` now recognized in addition to `boost`).
- Added synthetic calibration test to assert kickoff and touch detection after normalization.
- Confirmed measured frame rate is sane (20–60 Hz) for synthetic ~30 Hz sequence.

Changes
- src/rlcoach/normalize.py:
  - Accept `boost_amount` in dict player entries to populate PlayerFrame.boost_amount correctly.
- tests/test_events_calibration_synthetic.py:
  - New test building Rust-like frames (timestamp, ball {position, velocity, angular_velocity}, players[{...}]).
  - Asserts: normalization produces frames; measured Hz within 20–60; detectors return at least one KICKOFF and TOUCH; timeline includes both.

Notes
- Existing event thresholds (kickoff center tolerance and touch distance) proved sufficient for the synthetic sequence; no threshold changes required.
- Real replay gated E2E checks remain covered by the separate ticket.

Validation
- Ran full test suite: all tests passed (206/206).

