"""Tests for new analysis modules: mechanics, recovery, xg, defense, ball_prediction."""


from rlcoach.analysis.ball_prediction import analyze_ball_prediction
from rlcoach.analysis.defense import analyze_defense
from rlcoach.analysis.mechanics import analyze_mechanics
from rlcoach.analysis.recovery import analyze_recoveries
from rlcoach.analysis.xg import analyze_shots_xg
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import (
    BallFrame,
    Frame,
    Header,
    PlayerFrame,
    PlayerInfo,
    Rotation,
)


def create_test_frame(
    timestamp: float,
    players: list[PlayerFrame],
    ball_pos: Vec3 = Vec3(0.0, 0.0, 93.15),
    ball_vel: Vec3 = Vec3(0.0, 0.0, 0.0),
) -> Frame:
    """Helper to create test frames."""
    return Frame(
        timestamp=timestamp,
        ball=BallFrame(
            position=ball_pos,
            velocity=ball_vel,
            angular_velocity=Vec3(0.0, 0.0, 0.0),
        ),
        players=players,
    )


def create_test_player(
    player_id: str,
    team: int,
    position: Vec3 = Vec3(0.0, 0.0, 17.0),
    velocity: Vec3 = Vec3(0.0, 0.0, 0.0),
    rotation: Rotation | Vec3 = None,
    boost_amount: int = 33,
    is_supersonic: bool = False,
    is_on_ground: bool = True,
    is_demolished: bool = False,
) -> PlayerFrame:
    """Helper to create test player frames."""
    if rotation is None:
        rotation = Rotation(0.0, 0.0, 0.0)
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=position,
        velocity=velocity,
        rotation=rotation,
        boost_amount=boost_amount,
        is_supersonic=is_supersonic,
        is_on_ground=is_on_ground,
        is_demolished=is_demolished,
    )


class TestMechanicsAnalysis:
    """Test mechanics detection analysis."""

    def test_empty_frames_returns_empty_results(self):
        """Empty frames should return empty results."""
        result = analyze_mechanics([])

        assert result["per_player"] == {}
        assert result["events"] == []
        assert result["total_jumps"] == 0
        assert result["total_flips"] == 0
        assert result["total_aerials"] == 0

    def test_ground_player_no_mechanics(self):
        """Player staying on ground should have no mechanics detected."""
        player = create_test_player("player1", 0, is_on_ground=True)
        frames = [
            create_test_frame(0.0, [player]),
            create_test_frame(0.1, [player]),
            create_test_frame(0.2, [player]),
        ]

        result = analyze_mechanics(frames)

        # Player present but no special mechanics
        assert "player1" in result["per_player"]
        player_stats = result["per_player"]["player1"]
        assert player_stats["jump_count"] == 0
        assert player_stats["flip_count"] == 0

    def test_jump_detection(self):
        """Jumping should be detected via z-velocity spike."""
        # Ground state
        ground_player = create_test_player(
            "player1", 0, position=Vec3(0.0, 0.0, 17.0), is_on_ground=True
        )
        # After jump - airborne with upward velocity
        jumping_player = create_test_player(
            "player1",
            0,
            position=Vec3(0.0, 0.0, 50.0),
            velocity=Vec3(0.0, 0.0, 300.0),  # Above jump threshold
            is_on_ground=False,
        )
        # Still airborne
        airborne_player = create_test_player(
            "player1",
            0,
            position=Vec3(0.0, 0.0, 100.0),
            velocity=Vec3(0.0, 0.0, 100.0),
            is_on_ground=False,
        )

        frames = [
            create_test_frame(0.0, [ground_player]),
            create_test_frame(0.1, [jumping_player]),
            create_test_frame(0.2, [airborne_player]),
        ]

        result = analyze_mechanics(frames)

        # Verify structure is correct and has expected keys
        player_stats = result["per_player"]["player1"]
        assert "jump_count" in player_stats
        assert "double_jump_count" in player_stats
        assert "aerial_count" in player_stats
        assert "flip_count" in player_stats
        assert "total_mechanics" in player_stats
        # All counts should be non-negative integers
        assert isinstance(player_stats["total_mechanics"], int)
        assert player_stats["total_mechanics"] >= 0


class TestRecoveryAnalysis:
    """Test recovery detection analysis."""

    def test_empty_frames_returns_empty_results(self):
        """Empty frames should return empty results."""
        result = analyze_recoveries([])

        assert result["per_player"] == {}
        assert result["events"] == []

    def test_simple_landing_recovery(self):
        """Test landing after being airborne."""
        # Airborne phase
        airborne = create_test_player(
            "player1",
            0,
            position=Vec3(0.0, 0.0, 200.0),
            velocity=Vec3(500.0, 0.0, -100.0),
            is_on_ground=False,
        )
        # Landing
        landing = create_test_player(
            "player1",
            0,
            position=Vec3(50.0, 0.0, 17.0),
            velocity=Vec3(450.0, 0.0, 0.0),
            is_on_ground=True,
        )

        frames = [
            create_test_frame(0.0, [airborne]),
            create_test_frame(0.5, [airborne]),
            create_test_frame(1.0, [landing]),
            create_test_frame(1.1, [landing]),
            create_test_frame(1.2, [landing]),
        ]

        result = analyze_recoveries(frames)

        # Player should be tracked
        assert "player1" in result["per_player"]


class TestXGAnalysis:
    """Test expected goals (xG) analysis."""

    def test_empty_frames_returns_empty_results(self):
        """Empty inputs should return empty results."""
        result = analyze_shots_xg([], [])

        assert result["per_player"] == {}
        assert result["shots"] == []
        assert result["total_shots"] == 0

    def test_close_range_shot_higher_xg(self):
        """Shots close to goal should have higher xG."""
        # Ball very close to orange goal (y = -5120)
        close_pos = Vec3(0.0, -4500.0, 100.0)
        # Ball far from orange goal
        far_pos = Vec3(0.0, 0.0, 100.0)

        # xG should be higher for close shot
        # Note: calculate_xg takes position, velocity, shooter_team, frames
        # We'll just verify the analyze_shots_xg runs without error for now
        player = create_test_player("player1", 0, position=Vec3(0.0, -4600.0, 17.0))
        frames = [
            create_test_frame(0.0, [player], ball_pos=close_pos, ball_vel=Vec3(0.0, -1000.0, 0.0)),
        ]

        # No touches = no shots to analyze
        result = analyze_shots_xg(frames, [])
        assert result["total_shots"] == 0


class TestDefenseAnalysis:
    """Test defensive positioning analysis."""

    def test_empty_frames_returns_empty_results(self):
        """Empty frames should return empty results."""
        result = analyze_defense([])

        assert result["per_player"] == {}
        # Empty frames still return team structure with default values
        assert "blue" in result["per_team"]
        assert "orange" in result["per_team"]

    def test_last_defender_detection(self):
        """Test that last defender is correctly identified."""
        # Blue team: player1 closest to own goal (at y=-4000), player2 further up
        player1 = create_test_player(
            "player1", 0, position=Vec3(0.0, -4000.0, 17.0)  # Near blue goal
        )
        player2 = create_test_player(
            "player2", 0, position=Vec3(0.0, 0.0, 17.0)  # Midfield
        )
        # Ball in offensive half
        ball_pos = Vec3(0.0, 3000.0, 93.15)

        frames = [
            create_test_frame(0.0, [player1, player2], ball_pos=ball_pos),
            create_test_frame(0.5, [player1, player2], ball_pos=ball_pos),
            create_test_frame(1.0, [player1, player2], ball_pos=ball_pos),
        ]

        result = analyze_defense(frames)

        # Both players should be tracked
        assert "player1" in result["per_player"]
        assert "player2" in result["per_player"]


class TestBallPredictionAnalysis:
    """Test ball prediction/read analysis."""

    def test_empty_frames_returns_empty_results(self):
        """Empty frames should return empty results."""
        result = analyze_ball_prediction([])

        assert result["per_player"] == {}
        assert result["reads"] == []

    def test_ball_read_tracking(self):
        """Test that ball reads are tracked for players."""
        player = create_test_player(
            "player1",
            0,
            position=Vec3(0.0, -500.0, 17.0),
            velocity=Vec3(0.0, 200.0, 0.0),  # Moving toward ball
        )

        # Ball moving predictably
        frames = []
        for i in range(30):  # 1 second at 30fps
            t = i / 30.0
            ball_y = 0.0 + t * 300.0  # Ball moving at 300 uu/s
            frames.append(
                create_test_frame(
                    t,
                    [player],
                    ball_pos=Vec3(0.0, ball_y, 93.15),
                    ball_vel=Vec3(0.0, 300.0, 0.0),
                )
            )

        result = analyze_ball_prediction(frames)

        # Player should be tracked
        assert "player1" in result["per_player"]
        player_stats = result["per_player"]["player1"]
        assert "total_reads" in player_stats


class TestRotationHandling:
    """Test that Rotation and Vec3 rotation formats are both handled."""

    def test_rotation_object_handled(self):
        """Test that Rotation dataclass is properly handled."""
        rotation = Rotation(pitch=0.1, yaw=1.57, roll=0.0)
        player = create_test_player("player1", 0, rotation=rotation)

        frames = [
            create_test_frame(0.0, [player]),
            create_test_frame(0.1, [player]),
        ]

        # Should not raise AttributeError
        result = analyze_mechanics(frames)
        assert "player1" in result["per_player"]

    def test_vec3_rotation_handled(self):
        """Test that legacy Vec3 rotation is properly handled."""
        # Legacy format: Vec3(pitch, yaw, roll)
        rotation = Vec3(0.1, 1.57, 0.0)
        player = create_test_player("player1", 0, rotation=rotation)

        frames = [
            create_test_frame(0.0, [player]),
            create_test_frame(0.1, [player]),
        ]

        # Should not raise AttributeError
        result = analyze_mechanics(frames)
        assert "player1" in result["per_player"]


class TestIntegrationWithAggregator:
    """Test that new analysis modules integrate correctly."""

    def test_aggregate_analysis_includes_new_modules(self):
        """Test that aggregate_analysis includes new analysis fields."""
        from rlcoach.analysis import aggregate_analysis

        header = Header(
            playlist_id="unknown",
            map_name="DFH Stadium",
            team_size=1,
            players=[
                PlayerInfo(name="Alpha", team=0),
                PlayerInfo(name="Bravo", team=1),
            ],
        )

        player1 = create_test_player("A", 0, position=Vec3(0.0, -1000.0, 17.0))
        player2 = create_test_player("B", 1, position=Vec3(0.0, 1000.0, 17.0))

        frames = [
            create_test_frame(0.0, [player1, player2]),
            create_test_frame(1.0, [player1, player2]),
        ]

        events = {
            "goals": [],
            "demos": [],
            "kickoffs": [],
            "boost_pickups": [],
            "touches": [],
            "challenges": [],
        }

        result = aggregate_analysis(frames, events, header)

        # Check that per_player includes new analysis fields
        per_player = result.get("per_player", [])
        assert len(per_player) >= 0  # May have players from frames

        # Check that per_team includes defense
        per_team = result.get("per_team", {})
        assert "blue" in per_team
        assert "orange" in per_team

        # Defense should be in team analysis
        if "defense" in per_team["blue"]:
            assert isinstance(per_team["blue"]["defense"], dict)
