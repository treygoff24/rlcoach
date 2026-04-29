"""Regression coverage for advanced mechanics aggregation outputs."""

from __future__ import annotations

import pytest

from rlcoach.analysis import mechanics as mechanics_module
from rlcoach.analysis.mechanics import MechanicEvent, MechanicType
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, ParserTouchEvent, PlayerFrame


def _player(player_id: str, team: int) -> PlayerFrame:
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=Vec3(0.0, 0.0, 17.0),
        velocity=Vec3(0.0, 0.0, 0.0),
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=33,
    )


def _frame(players: list[PlayerFrame]) -> Frame:
    return Frame(
        timestamp=1.0,
        ball=BallFrame(
            position=Vec3(0.0, 0.0, 93.15),
            velocity=Vec3(0.0, 0.0, 0.0),
            angular_velocity=Vec3(0.0, 0.0, 0.0),
        ),
        players=players,
    )


@pytest.mark.parametrize(
    ("mechanic_type", "count_key"),
    [
        (MechanicType.FAST_AERIAL, "fast_aerial_count"),
        (MechanicType.FLIP_RESET, "flip_reset_count"),
        (MechanicType.AIR_ROLL, "air_roll_count"),
        (MechanicType.DRIBBLE, "dribble_count"),
        (MechanicType.FLICK, "flick_count"),
        (MechanicType.MUSTY_FLICK, "musty_flick_count"),
        (MechanicType.CEILING_SHOT, "ceiling_shot_count"),
        (MechanicType.POWER_SLIDE, "power_slide_count"),
        (MechanicType.GROUND_PINCH, "ground_pinch_count"),
        (MechanicType.DOUBLE_TOUCH, "double_touch_count"),
        (MechanicType.REDIRECT, "redirect_count"),
        (MechanicType.STALL, "stall_count"),
        (MechanicType.SKIM, "skim_count"),
        (MechanicType.PSYCHO, "psycho_count"),
    ],
)
def test_advanced_mechanics_have_positive_and_negative_count_paths(
    monkeypatch, mechanic_type: MechanicType, count_key: str
):
    frames = [_frame([_player("player_0", 0), _player("player_1", 1)])]
    event = MechanicEvent(
        timestamp=1.0,
        player_id="player_0",
        mechanic_type=mechanic_type,
        position=Vec3(0.0, 0.0, 17.0),
        velocity=Vec3(0.0, 0.0, 0.0),
    )

    def fake_detect(_frames: list[Frame], player_id: str):
        return [event] if player_id == "player_0" else []

    monkeypatch.setattr(mechanics_module, "detect_mechanics_for_player", fake_detect)
    result = mechanics_module.analyze_mechanics(frames)

    assert result["per_player"]["player_0"][count_key] == 1
    assert result["per_player"]["player_1"][count_key] == 0


def test_parser_touch_authority_drives_redirect_when_proximity_misses():
    """Sparse parser touches should be authoritative for contact-sensitive mechanics."""
    frames = [
        Frame(
            timestamp=0.0,
            ball=BallFrame(
                position=Vec3(0.0, 0.0, 500.0),
                velocity=Vec3(1000.0, 0.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    player_id="player_0",
                    team=0,
                    position=Vec3(2000.0, 0.0, 500.0),
                    velocity=Vec3(0.0, 0.0, 0.0),
                    rotation=Vec3(0.0, 0.0, 0.0),
                    boost_amount=33,
                    is_on_ground=True,
                )
            ],
        ),
        Frame(
            timestamp=0.1,
            ball=BallFrame(
                position=Vec3(0.0, 0.0, 500.0),
                velocity=Vec3(1000.0, 0.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    player_id="player_0",
                    team=0,
                    position=Vec3(2000.0, 0.0, 500.0),
                    velocity=Vec3(0.0, 0.0, 100.0),
                    rotation=Vec3(0.0, 0.0, 0.0),
                    boost_amount=33,
                    is_on_ground=False,
                )
            ],
        ),
        Frame(
            timestamp=0.2,
            ball=BallFrame(
                position=Vec3(0.0, 0.0, 500.0),
                velocity=Vec3(0.0, 1200.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    player_id="player_0",
                    team=0,
                    position=Vec3(2000.0, 0.0, 500.0),
                    velocity=Vec3(0.0, 0.0, 100.0),
                    rotation=Vec3(0.0, 0.0, 0.0),
                    boost_amount=33,
                    is_on_ground=False,
                )
            ],
            parser_touch_events=[
                ParserTouchEvent(timestamp=0.2, player_id="player_0", team=0)
            ],
        ),
    ]

    events = mechanics_module.detect_mechanics_for_player(frames, "player_0")

    assert any(event.mechanic_type == MechanicType.REDIRECT for event in events)


def test_parser_touch_authority_suppresses_proximity_redirect_false_positive():
    """When parser touch authority exists, no-touch frames must not infer contact."""
    frames = [
        Frame(
            timestamp=0.0,
            ball=BallFrame(
                position=Vec3(0.0, 0.0, 500.0),
                velocity=Vec3(1000.0, 0.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    player_id="player_0",
                    team=0,
                    position=Vec3(0.0, 0.0, 500.0),
                    velocity=Vec3(0.0, 0.0, 0.0),
                    rotation=Vec3(0.0, 0.0, 0.0),
                    boost_amount=33,
                    is_on_ground=True,
                ),
                PlayerFrame(
                    player_id="player_1",
                    team=1,
                    position=Vec3(1000.0, 0.0, 500.0),
                    velocity=Vec3(0.0, 0.0, 0.0),
                    rotation=Vec3(0.0, 0.0, 0.0),
                    boost_amount=33,
                    is_on_ground=True,
                ),
            ],
            parser_touch_events=[
                ParserTouchEvent(timestamp=0.0, player_id="player_1", team=1)
            ],
        ),
        Frame(
            timestamp=0.1,
            ball=BallFrame(
                position=Vec3(0.0, 0.0, 500.0),
                velocity=Vec3(1000.0, 0.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    player_id="player_0",
                    team=0,
                    position=Vec3(0.0, 0.0, 500.0),
                    velocity=Vec3(0.0, 0.0, 100.0),
                    rotation=Vec3(0.0, 0.0, 0.0),
                    boost_amount=33,
                    is_on_ground=False,
                )
            ],
        ),
        Frame(
            timestamp=0.2,
            ball=BallFrame(
                position=Vec3(0.0, 0.0, 500.0),
                velocity=Vec3(0.0, 1200.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0),
            ),
            players=[
                PlayerFrame(
                    player_id="player_0",
                    team=0,
                    position=Vec3(0.0, 0.0, 500.0),
                    velocity=Vec3(0.0, 0.0, 100.0),
                    rotation=Vec3(0.0, 0.0, 0.0),
                    boost_amount=33,
                    is_on_ground=False,
                )
            ],
            parser_touch_events=[],
        ),
    ]

    events = mechanics_module.detect_mechanics_for_player(frames, "player_0")

    assert not any(event.mechanic_type == MechanicType.REDIRECT for event in events)
