"""Contract tests for mechanics aggregation surfaces."""

from __future__ import annotations

from rlcoach.analysis import mechanics as mechanics_module
from rlcoach.analysis.mechanics import MechanicEvent, MechanicType
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame


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


def test_skim_and_psycho_counts_are_surfaced(monkeypatch):
    frames = [_frame([_player("player_0", 0), _player("player_1", 1)])]
    events = [
        MechanicEvent(
            timestamp=1.0,
            player_id="player_0",
            mechanic_type=MechanicType.SKIM,
            position=Vec3(0.0, 0.0, 17.0),
            velocity=Vec3(0.0, 0.0, 0.0),
        ),
        MechanicEvent(
            timestamp=1.2,
            player_id="player_0",
            mechanic_type=MechanicType.PSYCHO,
            position=Vec3(0.0, 0.0, 17.0),
            velocity=Vec3(0.0, 0.0, 0.0),
        ),
    ]

    def fake_detect(_frames: list[Frame], player_id: str):
        return events if player_id == "player_0" else []

    monkeypatch.setattr(mechanics_module, "detect_mechanics_for_player", fake_detect)
    result = mechanics_module.analyze_mechanics(frames)

    assert result["per_player"]["player_0"]["skim_count"] == 1
    assert result["per_player"]["player_0"]["psycho_count"] == 1
    assert result["per_player"]["player_1"]["skim_count"] == 0
    assert result["per_player"]["player_1"]["psycho_count"] == 0
    assert result["total_skims"] == 1
    assert result["total_psychos"] == 1
