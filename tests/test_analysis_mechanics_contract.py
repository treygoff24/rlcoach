"""Contract tests for mechanics aggregation surfaces."""

from __future__ import annotations

import rlcoach.analysis as analysis_module
from rlcoach.analysis import _analyze_player, aggregate_analysis
from rlcoach.analysis import mechanics as mechanics_module
from rlcoach.analysis.mechanics import MechanicEvent, MechanicType
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, Header, PlayerFrame, PlayerInfo


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


def test_player_mechanics_fallback_surfaces_advanced_zero_keys():
    result = _analyze_player(
        frames=[],
        events={
            "goals": [],
            "demos": [],
            "kickoffs": [],
            "boost_pickups": [],
            "touches": [],
            "challenges": [],
        },
        player_id="ghost",
        team="BLUE",
        header=Header(),
        cached_mechanics={"per_player": {}},
        cached_recoveries={"per_player": {}},
        cached_defense={"per_player": {}},
        cached_ball_prediction={"per_player": {}},
        cached_xg={"per_player": {}},
    )

    mechanics = result["mechanics"]
    assert mechanics["fast_aerial_count"] == 0
    assert mechanics["flip_reset_count"] == 0
    assert mechanics["air_roll_count"] == 0
    assert mechanics["air_roll_total_time_s"] == 0.0
    assert mechanics["dribble_count"] == 0
    assert mechanics["dribble_total_time_s"] == 0.0
    assert mechanics["musty_flick_count"] == 0
    assert mechanics["power_slide_count"] == 0
    assert mechanics["power_slide_total_time_s"] == 0.0
    assert mechanics["ground_pinch_count"] == 0
    assert mechanics["double_touch_count"] == 0
    assert mechanics["redirect_count"] == 0
    assert mechanics["stall_count"] == 0
    assert mechanics["skim_count"] == 0
    assert mechanics["psycho_count"] == 0


def test_team_mechanics_match_per_player_totals(monkeypatch):
    frames = [_frame([_player("player_0", 0), _player("player_1", 1)])]
    header = Header(
        players=[
            PlayerInfo(name="Blue", team=0),
            PlayerInfo(name="Orange", team=1),
        ]
    )

    cached_mechanics = {
        "per_player": {
            "player_0": {
                "jump_count": 1,
                "double_jump_count": 1,
                "flip_count": 2,
                "wavedash_count": 3,
                "aerial_count": 4,
                "halfflip_count": 5,
                "speedflip_count": 6,
                "flip_cancel_count": 7,
                "fast_aerial_count": 8,
                "flip_reset_count": 9,
                "air_roll_count": 19,
                "air_roll_total_time_s": 1.5,
                "dribble_count": 10,
                "dribble_total_time_s": 2.5,
                "flick_count": 11,
                "musty_flick_count": 20,
                "ceiling_shot_count": 12,
                "power_slide_count": 21,
                "power_slide_total_time_s": 3.5,
                "ground_pinch_count": 13,
                "double_touch_count": 14,
                "redirect_count": 15,
                "stall_count": 16,
                "skim_count": 17,
                "psycho_count": 18,
                "total_mechanics": 152,
            },
            "player_1": {
                "jump_count": 20,
                "double_jump_count": 21,
                "flip_count": 22,
                "wavedash_count": 23,
                "aerial_count": 24,
                "halfflip_count": 25,
                "speedflip_count": 26,
                "flip_cancel_count": 27,
                "fast_aerial_count": 28,
                "flip_reset_count": 29,
                "air_roll_count": 0,
                "air_roll_total_time_s": 0.0,
                "dribble_count": 30,
                "dribble_total_time_s": 0.0,
                "flick_count": 31,
                "musty_flick_count": 0,
                "ceiling_shot_count": 32,
                "power_slide_count": 0,
                "power_slide_total_time_s": 0.0,
                "ground_pinch_count": 33,
                "double_touch_count": 34,
                "redirect_count": 35,
                "stall_count": 36,
                "skim_count": 37,
                "psycho_count": 38,
                "total_mechanics": 430,
            },
        },
        "events": [],
    }

    monkeypatch.setattr(
        analysis_module, "analyze_mechanics", lambda _frames: cached_mechanics
    )

    result = aggregate_analysis(
        frames,
        {
            "goals": [],
            "demos": [],
            "kickoffs": [],
            "boost_pickups": [],
            "touches": [],
            "challenges": [],
        },
        header,
    )

    blue = result["per_team"]["blue"]["mechanics"]
    orange = result["per_team"]["orange"]["mechanics"]

    assert blue["total_wavedashes"] == 3
    assert blue["total_halfflips"] == 5
    assert blue["total_speedflips"] == 6
    assert blue["total_aerials"] == 4
    assert blue["total_flips"] == 2
    assert blue["total_flip_cancels"] == 7
    assert blue["total_fast_aerials"] == 8
    assert blue["total_flip_resets"] == 9
    assert blue["total_air_rolls"] == 19
    assert blue["total_air_roll_time_s"] == 1.5
    assert blue["total_dribbles"] == 10
    assert blue["total_dribble_time_s"] == 2.5
    assert blue["total_flicks"] == 11
    assert blue["total_musty_flicks"] == 20
    assert blue["total_ceiling_shots"] == 12
    assert blue["total_power_slides"] == 21
    assert blue["total_power_slide_time_s"] == 3.5
    assert blue["total_ground_pinches"] == 13
    assert blue["total_double_touches"] == 14
    assert blue["total_redirects"] == 15
    assert blue["total_stalls"] == 16
    assert blue["total_skims"] == 17
    assert blue["total_psychos"] == 18
    assert blue["total_mechanics"] == 152
    assert orange["total_wavedashes"] == 23
    assert orange["total_psychos"] == 38
