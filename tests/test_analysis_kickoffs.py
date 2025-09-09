"""Tests for kickoff analysis."""

from rlcoach.analysis.kickoffs import analyze_kickoffs
from rlcoach.events import KickoffEvent
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import Frame, PlayerFrame, BallFrame


def make_frame(t: float, players: list[PlayerFrame]) -> Frame:
    return Frame(
        timestamp=t,
        ball=BallFrame(
            position=Vec3(0.0, 0.0, 93.15),
            velocity=Vec3(0.0, 0.0, 0.0),
            angular_velocity=Vec3(0.0, 0.0, 0.0),
        ),
        players=players,
    )


def make_player(pid: str, team: int) -> PlayerFrame:
    return PlayerFrame(
        player_id=pid,
        team=team,
        position=Vec3(0.0, 0.0, 17.0),
        velocity=Vec3(0.0, 0.0, 0.0),
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=33,
        is_supersonic=False,
        is_on_ground=True,
        is_demolished=False,
    )


class TestKickoffAnalysis:
    def test_team_kickoff_counts_and_approaches(self):
        # Two blue, two orange players to map teams
        p1 = make_player("b1", 0)
        p2 = make_player("b2", 0)
        p3 = make_player("o1", 1)
        p4 = make_player("o2", 1)

        frames = [make_frame(0.0, [p1, p2, p3, p4]), make_frame(1.0, [p1, p2, p3, p4])]

        # Two kickoff events
        k1 = KickoffEvent(
            phase="INITIAL",
            t_start=0.0,
            players=[
                {"player_id": "b1", "role": "GO", "boost_used": 10.0, "approach_type": "SPEEDFLIP", "time_to_first_touch": 1.4},
                {"player_id": "o1", "role": "GO", "boost_used": 8.0, "approach_type": "STANDARD", "time_to_first_touch": 1.6},
            ],
            outcome="FIRST_POSSESSION_BLUE",
        )
        k2 = KickoffEvent(
            phase="INITIAL",
            t_start=60.0,
            players=[
                {"player_id": "b2", "role": "BACK", "boost_used": 0.0, "approach_type": "FAKE", "time_to_first_touch": None},
                {"player_id": "o2", "role": "BACK", "boost_used": 0.0, "approach_type": "DELAY", "time_to_first_touch": None},
            ],
            outcome="NEUTRAL",
        )

        events = {"kickoffs": [k1, k2]}

        # Team BLUE analysis
        blue = analyze_kickoffs(frames, events, team="BLUE")
        assert blue["count"] == 2
        assert blue["first_possession"] == 1
        assert blue["neutral"] == 1
        assert blue["goals_for"] == 0
        assert blue["goals_against"] == 0
        assert abs(blue["avg_time_to_first_touch_s"] - 1.4) < 1e-6
        assert blue["approach_types"]["SPEEDFLIP"] == 1
        assert blue["approach_types"]["FAKE"] == 1

        # Team ORANGE analysis
        orange = analyze_kickoffs(frames, events, team="ORANGE")
        assert orange["count"] == 2
        assert orange["first_possession"] == 0
        assert orange["neutral"] == 1
        assert orange["approach_types"]["STANDARD"] == 1
        assert orange["approach_types"]["DELAY"] == 1

    def test_player_kickoff_aggregation(self):
        p1 = make_player("b1", 0)
        p3 = make_player("o1", 1)
        frames = [make_frame(0.0, [p1, p3])]
        k = KickoffEvent(
            phase="INITIAL",
            t_start=0.0,
            players=[
                {"player_id": "b1", "role": "GO", "boost_used": 12.0, "approach_type": "UNKNOWN", "time_to_first_touch": 1.2},
                {"player_id": "o1", "role": "GO", "boost_used": 9.0, "approach_type": "STANDARD", "time_to_first_touch": 1.6},
            ],
            outcome="FIRST_POSSESSION_BLUE",
        )
        events = {"kickoffs": [k]}

        res = analyze_kickoffs(frames, events, player_id="b1")
        assert res["count"] == 1
        assert res["neutral"] == 0
        assert abs(res["avg_time_to_first_touch_s"] - 1.2) < 1e-6
        assert res["approach_types"]["UNKNOWN"] == 1

