"""Synthetic calibration test for normalization and event detectors.

Builds a minimal sequence of dict-shaped frames that mimic the Rust adapter
output and asserts that normalization ingests them and detectors fire
for kickoff and touch events.
"""

from rlcoach.normalize import build_timeline, measure_frame_rate
from rlcoach.events import (
    detect_kickoffs,
    detect_touches,
    detect_challenge_events,
    build_timeline as build_events_timeline,
)
from rlcoach.parser.types import Header, PlayerInfo


def _rust_like_frame(ts, ball_pos, ball_vel, players):
    return {
        "timestamp": ts,
        "ball": {
            "position": {"x": ball_pos[0], "y": ball_pos[1], "z": ball_pos[2]},
            "velocity": {"x": ball_vel[0], "y": ball_vel[1], "z": ball_vel[2]},
            "angular_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "players": players,
    }


def _rust_like_player(pid, team, pos, vel=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), boost=33,
                      supersonic=False, on_ground=True, demolished=False):
    return {
        "player_id": pid,
        "team": team,
        "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
        "velocity": {"x": vel[0], "y": vel[1], "z": vel[2]},
        "rotation": {"x": rot[0], "y": rot[1], "z": rot[2]},
        "boost_amount": boost,
        "is_supersonic": bool(supersonic),
        "is_on_ground": bool(on_ground),
        "is_demolished": bool(demolished),
    }


def test_normalization_and_events_from_rust_like_frames():
    # Header with two players
    header = Header(
        players=[
            PlayerInfo(name="Blue", team=0),
            PlayerInfo(name="Orange", team=1),
        ]
    )

    # Build a short kickoff + touch sequence at ~30 Hz
    frames = []
    # Two stationary frames at center (kickoff phase)
    frames.append(
        _rust_like_frame(
            0.0,
            (0.0, 0.0, 93.15),
            (0.0, 0.0, 0.0),
            [
                _rust_like_player("p_blue", 0, (-500.0, -1000.0, 17.0), boost=50),
                _rust_like_player("p_orange", 1, (500.0, 1000.0, 17.0), boost=60),
            ],
        )
    )
    frames.append(
        _rust_like_frame(
            1 / 30.0,
            (0.0, 0.0, 93.15),
            (0.0, 0.0, 0.0),
            [
                _rust_like_player("p_blue", 0, (-200.0, -800.0, 17.0), boost=48),
                _rust_like_player("p_orange", 1, (200.0, 800.0, 17.0), boost=58),
            ],
        )
    )
    # Ball moves away from center (kickoff ends) and Orange touches ball
    frames.append(
        _rust_like_frame(
            2 / 30.0,
            (100.0, 120.0, 100.0),
            (400.0, 600.0, 50.0),
            [
                _rust_like_player("p_blue", 0, (50.0, -50.0, 17.0), boost=45),
                _rust_like_player("p_orange", 1, (110.0, 120.0, 17.0), boost=55),  # Near ball
            ],
        )
    )

    # Normalize frames
    normalized = build_timeline(header, frames)

    # Frame rate should be sane (20..60 Hz)
    hz = measure_frame_rate(normalized)
    assert 20.0 <= hz <= 60.0

    # Detect events
    kos = detect_kickoffs(normalized, header)
    touches = detect_touches(normalized)
    challenge_events = detect_challenge_events(normalized, touches)

    assert len(kos) >= 1
    assert len(touches) >= 1
    assert kos[0].players  # enriched kickoff payload
    assert isinstance(kos[0].players[0].get("boost_used"), float)

    # Timeline includes KICKOFF and TOUCH entries
    timeline = build_events_timeline({
        "goals": [],
        "demos": [],
        "kickoffs": kos,
        "boost_pickups": [],
        "touches": touches,
        "challenges": challenge_events,
    })
    kinds = [t.type for t in timeline]
    assert "KICKOFF" in kinds
    assert "TOUCH" in kinds
    assert "SHOT" in kinds or "TOUCH" in kinds  # shot emission optional in synthetic data
