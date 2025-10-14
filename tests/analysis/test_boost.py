"""Targeted boost analysis tests for Ballchasing parity."""

from __future__ import annotations

from rlcoach.analysis.boost import analyze_boost
from rlcoach.events import BoostPickupEvent, detect_boost_pickups
from rlcoach.field_constants import Vec3, FIELD
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame


def create_frame(timestamp: float, players: list[PlayerFrame]) -> Frame:
    """Utility to build a minimal frame with static ball state."""
    ball = BallFrame(
        position=Vec3(0.0, 0.0, 93.15),
        velocity=Vec3(0.0, 0.0, 0.0),
        angular_velocity=Vec3(0.0, 0.0, 0.0),
    )
    return Frame(timestamp=timestamp, ball=ball, players=players)


def create_player(
    player_id: str,
    team: int,
    position: Vec3,
    boost: float,
    velocity: Vec3 | None = None,
) -> PlayerFrame:
    """Utility to build a player snapshot."""
    if velocity is None:
        velocity = Vec3(0.0, 0.0, 0.0)
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=position,
        velocity=velocity,
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=int(boost),
        is_supersonic=False,
        is_on_ground=True,
        is_demolished=False,
    )


def test_detects_big_and_small_pad_pickups():
    """Boost detector maps frame deltas to canonical big/small pad ids."""
    big_pad = FIELD.BOOST_PADS[0]  # Blue back-left corner
    small_pad = FIELD.BOOST_PADS[11]  # Neutral mid-small pad (-1024, y<0)

    frames = [
        create_frame(
            0.0,
            [
                create_player("p1", 0, Vec3(big_pad.position.x, big_pad.position.y, 17.0), 0),
            ],
        ),
        create_frame(
            0.1,
            [
                create_player("p1", 0, Vec3(big_pad.position.x, big_pad.position.y, 17.0), 100),
            ],
        ),
        create_frame(
            4.5,
            [
                create_player("p1", 0, Vec3(small_pad.position.x, small_pad.position.y, 17.0), 60),
            ],
        ),
        create_frame(
            4.6,
            [
                create_player("p1", 0, Vec3(small_pad.position.x, small_pad.position.y, 17.0), 72),
            ],
        ),
    ]

    pickups = detect_boost_pickups(frames)
    assert len(pickups) == 2
    pad_types = {pickup.pad_type for pickup in pickups}
    pad_ids = {pickup.pad_id for pickup in pickups}
    assert pad_types == {"BIG", "SMALL"}
    assert pad_ids == {big_pad.pad_id, small_pad.pad_id}


def test_detects_stolen_boost_flags():
    """Boost detector tags pickups on opponent half as stolen."""
    orange_big_pad = FIELD.BOOST_PADS[3]  # Blue steals orange corner
    blue_small_pad = FIELD.BOOST_PADS[10]  # Orange steals blue small pad
    mid_orange_small_pad = FIELD.BOOST_PADS[24]  # Midfield-but-opponent small pad (y=2300)

    frames = [
        create_frame(
            1.0,
            [
                create_player("blue_p", 0, Vec3(orange_big_pad.position.x, orange_big_pad.position.y, 17.0), 20),
                create_player("orange_p", 1, Vec3(blue_small_pad.position.x, blue_small_pad.position.y, 17.0), 30),
                create_player("blue_mid", 0, Vec3(mid_orange_small_pad.position.x, mid_orange_small_pad.position.y, 17.0), 10),
            ],
        ),
        create_frame(
            1.1,
            [
                create_player("blue_p", 0, Vec3(orange_big_pad.position.x, orange_big_pad.position.y, 17.0), 120),
                create_player("orange_p", 1, Vec3(blue_small_pad.position.x, blue_small_pad.position.y, 17.0), 42),
                create_player("blue_mid", 0, Vec3(mid_orange_small_pad.position.x, mid_orange_small_pad.position.y, 17.0), 22),
            ],
        ),
    ]

    pickups = detect_boost_pickups(frames)
    assert len(pickups) == 3

    stolen_lookup = {pickup.player_id: pickup.stolen for pickup in pickups}
    assert stolen_lookup["blue_p"] is True
    assert stolen_lookup["orange_p"] is True
    assert stolen_lookup["blue_mid"] is True


def test_overfill_and_waste_metrics():
    """Analyzer combines overfill and waste calculations with updated thresholds."""
    frames = [
        create_frame(
            0.0,
            [
                create_player("p1", 0, Vec3(0.0, 0.0, 17.0), 90, Vec3(2400.0, 0.0, 0.0)),
            ],
        ),
        create_frame(
            5.0,
            [
                create_player("p1", 0, Vec3(0.0, 0.0, 17.0), 70, Vec3(2400.0, 0.0, 0.0)),
            ],
        ),
        create_frame(
            6.0,
            [
                create_player("p1", 0, Vec3(0.0, -4240.0, 17.0), 70, Vec3(0.0, 0.0, 0.0)),
            ],
        ),
        create_frame(
            6.1,
            [
                create_player("p1", 0, Vec3(0.0, -4240.0, 17.0), 82, Vec3(0.0, 0.0, 0.0)),
            ],
        ),
        create_frame(
            12.0,
            [
                create_player("p1", 0, Vec3(3584.0, -4096.0, 17.0), 95, Vec3(0.0, 0.0, 0.0)),
            ],
        ),
        create_frame(
            12.1,
            [
                create_player("p1", 0, Vec3(3584.0, -4096.0, 17.0), 100, Vec3(0.0, 0.0, 0.0)),
            ],
        ),
    ]

    small_pad = FIELD.BOOST_PADS[6]  # (-3584, -2484)
    big_pad = FIELD.BOOST_PADS[0]
    pickups = [
        BoostPickupEvent(
            t=6.1,
            player_id="p1",
            pad_type="SMALL",
            stolen=False,
            pad_id=small_pad.pad_id,
            location=small_pad.position,
            frame=3,
            boost_before=70.0,
            boost_after=82.0,
            boost_gain=12.0,
        ),
        BoostPickupEvent(
            t=12.1,
            player_id="p1",
            pad_type="BIG",
            stolen=False,
            pad_id=big_pad.pad_id,
            location=big_pad.position,
            frame=5,
            boost_before=95.0,
            boost_after=100.0,
            boost_gain=5.0,
        ),
    ]

    events = {"boost_pickups": pickups}
    result = analyze_boost(frames, events, player_id="p1")

    assert result["overfill"] == 95.0  # Big pad waste: 100 capacity - 5 gain = 95 wasted units
    assert result["waste"] > 0.0  # Supersonic consumption detected between 0-5 seconds


def test_merge_window_keeps_same_pad():
    """Merge window should consolidate multi-frame refills into a single pad event."""
    pad = FIELD.BOOST_PADS[0]
    frames = [
        create_frame(
            0.0,
            [
                create_player("p1", 0, Vec3(pad.position.x, pad.position.y, 17.0), 0),
            ],
        ),
        create_frame(
            0.1,
            [
                create_player("p1", 0, Vec3(pad.position.x, pad.position.y, 17.0), 40),
            ],
        ),
        create_frame(
            0.3,
            [
                create_player("p1", 0, Vec3(pad.position.x, pad.position.y, 17.0), 80),
            ],
        ),
        create_frame(
            0.5,
            [
                create_player("p1", 0, Vec3(pad.position.x, pad.position.y, 17.0), 100),
            ],
        ),
    ]

    pickups = detect_boost_pickups(frames)
    assert len(pickups) == 1
    pickup = pickups[0]
    assert pickup.pad_id == pad.pad_id
    assert pickup.boost_gain == 100.0
