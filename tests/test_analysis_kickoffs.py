"""Tests for kickoff analysis."""

from rlcoach.analysis.kickoffs import analyze_kickoffs, APPROACH_KEYS
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


class TestApproachKeys:
    """Tests for new approach type keys."""

    def test_approach_keys_contains_all_new_types(self):
        """Verify all new approach types are in APPROACH_KEYS."""
        expected = [
            "SPEEDFLIP",
            "STANDARD_FRONTFLIP",
            "STANDARD_DIAGONAL",
            "STANDARD_WAVEDASH",
            "STANDARD_BOOST",
            "DELAY",
            "FAKE_STATIONARY",
            "FAKE_HALFFLIP",
            "FAKE_AGGRESSIVE",
            "STANDARD",
            "UNKNOWN",
        ]
        assert APPROACH_KEYS == expected

    def test_all_approach_types_registered(self):
        """All standard and fake subtypes are in the key list."""
        assert "STANDARD_FRONTFLIP" in APPROACH_KEYS
        assert "STANDARD_DIAGONAL" in APPROACH_KEYS
        assert "FAKE_STATIONARY" in APPROACH_KEYS
        assert "FAKE_HALFFLIP" in APPROACH_KEYS
        assert "FAKE_AGGRESSIVE" in APPROACH_KEYS


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
                {"player_id": "b2", "role": "BACK", "boost_used": 0.0, "approach_type": "FAKE_STATIONARY", "time_to_first_touch": None},
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
        assert blue["approach_types"]["FAKE_STATIONARY"] == 1

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


class TestKickoffApproachTypeVariants:
    """Tests for new approach type variants in kickoff analysis."""

    def test_new_fake_subtypes_aggregation(self):
        """Test that all FAKE subtypes are aggregated correctly."""
        p1 = make_player("b1", 0)
        p2 = make_player("o1", 1)
        frames = [make_frame(0.0, [p1, p2])]

        # Create kickoffs with different fake subtypes
        k1 = KickoffEvent(
            phase="INITIAL",
            t_start=0.0,
            players=[
                {"player_id": "b1", "role": "BACK", "boost_used": 0.0, "approach_type": "FAKE_STATIONARY", "time_to_first_touch": None},
                {"player_id": "o1", "role": "BACK", "boost_used": 5.0, "approach_type": "FAKE_HALFFLIP", "time_to_first_touch": None},
            ],
            outcome="NEUTRAL",
        )
        k2 = KickoffEvent(
            phase="INITIAL",
            t_start=60.0,
            players=[
                {"player_id": "b1", "role": "BACK", "boost_used": 15.0, "approach_type": "FAKE_AGGRESSIVE", "time_to_first_touch": None},
                {"player_id": "o1", "role": "BACK", "boost_used": 0.0, "approach_type": "FAKE_STATIONARY", "time_to_first_touch": None},
            ],
            outcome="NEUTRAL",
        )
        events = {"kickoffs": [k1, k2]}

        blue = analyze_kickoffs(frames, events, team="BLUE")
        assert blue["approach_types"]["FAKE_STATIONARY"] == 1
        assert blue["approach_types"]["FAKE_AGGRESSIVE"] == 1
        assert blue["approach_types"]["FAKE_HALFFLIP"] == 0

        orange = analyze_kickoffs(frames, events, team="ORANGE")
        assert orange["approach_types"]["FAKE_HALFFLIP"] == 1
        assert orange["approach_types"]["FAKE_STATIONARY"] == 1
        assert orange["approach_types"]["FAKE_AGGRESSIVE"] == 0

    def test_new_standard_subtypes_aggregation(self):
        """Test that all STANDARD subtypes are aggregated correctly."""
        p1 = make_player("b1", 0)
        p2 = make_player("o1", 1)
        frames = [make_frame(0.0, [p1, p2])]

        k1 = KickoffEvent(
            phase="INITIAL",
            t_start=0.0,
            players=[
                {"player_id": "b1", "role": "GO", "boost_used": 20.0, "approach_type": "STANDARD_FRONTFLIP", "time_to_first_touch": 2.0},
                {"player_id": "o1", "role": "GO", "boost_used": 25.0, "approach_type": "STANDARD_DIAGONAL", "time_to_first_touch": 1.9},
            ],
            outcome="FIRST_POSSESSION_ORANGE",
        )
        k2 = KickoffEvent(
            phase="INITIAL",
            t_start=60.0,
            players=[
                {"player_id": "b1", "role": "GO", "boost_used": 15.0, "approach_type": "STANDARD_BOOST", "time_to_first_touch": 2.2},
                {"player_id": "o1", "role": "GO", "boost_used": 22.0, "approach_type": "STANDARD_WAVEDASH", "time_to_first_touch": 1.95},
            ],
            outcome="FIRST_POSSESSION_ORANGE",
        )
        events = {"kickoffs": [k1, k2]}

        blue = analyze_kickoffs(frames, events, team="BLUE")
        assert blue["approach_types"]["STANDARD_FRONTFLIP"] == 1
        assert blue["approach_types"]["STANDARD_BOOST"] == 1
        assert blue["approach_types"]["STANDARD_DIAGONAL"] == 0

        orange = analyze_kickoffs(frames, events, team="ORANGE")
        assert orange["approach_types"]["STANDARD_DIAGONAL"] == 1
        assert orange["approach_types"]["STANDARD_WAVEDASH"] == 1

    def test_mixed_approach_types_player_level(self):
        """Test aggregation at player level with mixed approach types."""
        p1 = make_player("b1", 0)
        p2 = make_player("o1", 1)
        frames = [make_frame(0.0, [p1, p2])]

        kickoffs = [
            KickoffEvent(
                phase="INITIAL",
                t_start=0.0,
                players=[
                    {"player_id": "b1", "role": "GO", "boost_used": 25.0, "approach_type": "SPEEDFLIP", "time_to_first_touch": 2.5},
                    {"player_id": "o1", "role": "GO", "boost_used": 20.0, "approach_type": "STANDARD", "time_to_first_touch": 2.8},
                ],
                outcome="FIRST_POSSESSION_BLUE",
            ),
            KickoffEvent(
                phase="INITIAL",
                t_start=60.0,
                players=[
                    {"player_id": "b1", "role": "GO", "boost_used": 25.0, "approach_type": "SPEEDFLIP", "time_to_first_touch": 2.4},
                    {"player_id": "o1", "role": "GO", "boost_used": 0.0, "approach_type": "DELAY", "time_to_first_touch": 2.9},
                ],
                outcome="FIRST_POSSESSION_BLUE",
            ),
            KickoffEvent(
                phase="INITIAL",
                t_start=120.0,
                players=[
                    {"player_id": "b1", "role": "GO", "boost_used": 22.0, "approach_type": "STANDARD_DIAGONAL", "time_to_first_touch": 2.7},
                    {"player_id": "o1", "role": "GO", "boost_used": 0.0, "approach_type": "FAKE_STATIONARY", "time_to_first_touch": None},
                ],
                outcome="FIRST_POSSESSION_BLUE",
            ),
        ]
        events = {"kickoffs": kickoffs}

        # Player b1's approach distribution
        b1_result = analyze_kickoffs(frames, events, player_id="b1")
        assert b1_result["approach_types"]["SPEEDFLIP"] == 2
        assert b1_result["approach_types"]["STANDARD_DIAGONAL"] == 1
        assert b1_result["count"] == 3

        # Player o1's approach distribution
        o1_result = analyze_kickoffs(frames, events, player_id="o1")
        assert o1_result["approach_types"]["STANDARD"] == 1
        assert o1_result["approach_types"]["DELAY"] == 1
        assert o1_result["approach_types"]["FAKE_STATIONARY"] == 1
        assert o1_result["count"] == 3

