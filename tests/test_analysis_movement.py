"""Tests for movement analysis."""

import math

import pytest

from rlcoach.analysis.movement import (
    _calculate_speed,
    _uu_s_to_kph,
    _uu_to_km,
    analyze_movement,
)
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame


def create_test_frame(timestamp: float, players: list[PlayerFrame]) -> Frame:
    """Helper to create test frames."""
    return Frame(
        timestamp=timestamp,
        ball=BallFrame(
            position=Vec3(0.0, 0.0, 93.15),
            velocity=Vec3(0.0, 0.0, 0.0),
            angular_velocity=Vec3(0.0, 0.0, 0.0)
        ),
        players=players
    )


def create_test_player(
    player_id: str, 
    team: int,
    position: Vec3 = Vec3(0.0, 0.0, 17.0),
    velocity: Vec3 = Vec3(0.0, 0.0, 0.0),
    rotation: Vec3 = Vec3(0.0, 0.0, 0.0),
    boost_amount: int = 33,
    is_supersonic: bool = False,
    is_on_ground: bool = True,
    is_demolished: bool = False
) -> PlayerFrame:
    """Helper to create test player frames."""
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=position,
        velocity=velocity,
        rotation=rotation,
        boost_amount=boost_amount,
        is_supersonic=is_supersonic,
        is_on_ground=is_on_ground,
        is_demolished=is_demolished
    )


class TestMovementAnalysis:
    """Test movement analysis functions."""
    
    def test_empty_frames_returns_zeros(self):
        """Empty frames should return all zero metrics."""
        frames = []
        events = {}
        
        result = analyze_movement(frames, events, player_id="player1")
        
        assert result["avg_speed_kph"] == 0.0
        assert result["distance_km"] == 0.0
        assert result["max_speed_kph"] == 0.0
        assert result["time_slow_s"] == 0.0
        assert result["time_boost_speed_s"] == 0.0
        assert result["time_supersonic_s"] == 0.0
        assert result["time_ground_s"] == 0.0
        assert result["time_low_air_s"] == 0.0
        assert result["time_high_air_s"] == 0.0
        assert result["powerslide_count"] == 0
        assert result["powerslide_duration_s"] == 0.0
        assert result["aerial_count"] == 0
        assert result["aerial_time_s"] == 0.0
    
    def test_speed_bucket_classification(self):
        """Test speed bucket classification with different velocities."""
        players = [
            # Slow speed (200 UU/s)
            create_test_player("player1", 0, velocity=Vec3(200.0, 0.0, 0.0)),
            # Boost speed (ground speed 1800 UU/s)
            create_test_player("player1", 0, velocity=Vec3(1800.0, 0.0, 0.0)),
            # Supersonic speed (2500 UU/s)
            create_test_player("player1", 0, velocity=Vec3(2500.0, 0.0, 0.0), is_supersonic=True),
        ]
        
        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(1.0, [players[1]]),
            create_test_frame(2.0, [players[2]]),
        ]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Each frame is ~1 second apart
        assert result["time_slow_s"] == 1.0
        assert result["time_boost_speed_s"] == 1.0
        assert result["time_supersonic_s"] == 1.0
        
        # Average speed calculation
        avg_speed_uu_s = (200.0 + 1800.0 + 2500.0) / 3
        expected_avg_kph = _uu_s_to_kph(avg_speed_uu_s)
        assert abs(result["avg_speed_kph"] - expected_avg_kph) < 0.01

    def test_distance_accumulation(self):
        """Distance should accumulate from frame-to-frame position deltas."""
        players = [
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 0.0)),
            create_test_player("player1", 0, position=Vec3(1000.0, 0.0, 0.0)),
            create_test_player("player1", 0, position=Vec3(2000.0, 0.0, 0.0)),
        ]

        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(1.0, [players[1]]),
            create_test_frame(2.0, [players[2]]),
        ]

        result = analyze_movement(frames, {}, player_id="player1")

        expected_distance_km = round(_uu_to_km(2000.0), 2)
        assert result["distance_km"] == pytest.approx(expected_distance_km, rel=1e-3)

    def test_max_speed_tracking(self):
        """Max speed should reflect the highest observed speed."""
        players = [
            create_test_player("player1", 0, velocity=Vec3(500.0, 0.0, 0.0)),
            create_test_player("player1", 0, velocity=Vec3(1500.0, 0.0, 0.0)),
            create_test_player("player1", 0, velocity=Vec3(2500.0, 0.0, 0.0)),
        ]

        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(1.0, [players[1]]),
            create_test_frame(2.0, [players[2]]),
        ]

        result = analyze_movement(frames, {}, player_id="player1")

        expected_max_kph = round(_uu_s_to_kph(2500.0), 2)
        assert result["max_speed_kph"] == pytest.approx(expected_max_kph, rel=1e-3)
    
    def test_ground_vs_air_classification(self):
        """Test ground vs air time classification."""
        players = [
            # On ground
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 17.0), is_on_ground=True),
            # Low air
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 100.0), is_on_ground=False),
            # High air
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 600.0), is_on_ground=False),
        ]
        
        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(1.0, [players[1]]),
            create_test_frame(2.0, [players[2]]),
        ]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        assert result["time_ground_s"] == 1.0
        assert result["time_low_air_s"] == 1.0
        assert result["time_high_air_s"] == 1.0
    
    def test_powerslide_detection(self):
        """Test powerslide detection based on angular velocity."""
        # Create frames with rotation changes indicating powersliding
        players = [
            # Starting position
            create_test_player("player1", 0, rotation=Vec3(0.0, 0.0, 0.0), is_on_ground=True),
            # High angular velocity (powersliding)
            create_test_player("player1", 0, rotation=Vec3(0.0, 1.0, 0.0), is_on_ground=True),
            create_test_player("player1", 0, rotation=Vec3(0.0, 2.0, 0.0), is_on_ground=True),
            create_test_player("player1", 0, rotation=Vec3(0.0, 3.0, 0.0), is_on_ground=True),
            # Back to normal
            create_test_player("player1", 0, rotation=Vec3(0.0, 3.1, 0.0), is_on_ground=True),
        ]
        
        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(0.1, [players[1]]),  # High angular velocity starts
            create_test_frame(0.2, [players[2]]),  # Continuing
            create_test_frame(0.3, [players[3]]),  # Continuing
            create_test_frame(0.4, [players[4]]),  # Back to normal
        ]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Should detect at least one powerslide
        assert result["powerslide_count"] >= 1
        assert result["powerslide_duration_s"] > 0.0
    
    def test_aerial_detection(self):
        """Test aerial detection based on height and duration."""
        players = [
            # On ground
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 17.0), is_on_ground=True),
            # Taking off
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 250.0), is_on_ground=False),
            # High in air (aerial)
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 400.0), is_on_ground=False),
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 500.0), is_on_ground=False),
            # Landing
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 100.0), is_on_ground=False),
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 17.0), is_on_ground=True),
        ]
        
        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(0.5, [players[1]]),  # Start aerial
            create_test_frame(1.0, [players[2]]),  # Continuing aerial  
            create_test_frame(1.5, [players[3]]),  # Still in aerial
            create_test_frame(2.0, [players[4]]),  # End aerial
            create_test_frame(2.5, [players[5]]),
        ]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Should detect one aerial that meets minimum duration
        assert result["aerial_count"] >= 1
        assert result["aerial_time_s"] > 0.5

    def test_frame_duration_fallback_for_duplicate_timestamps(self):
        """Ensure duration fallback keeps analysis progressing when timestamps repeat."""
        frames = [
            create_test_frame(0.0, [create_test_player("player1", 0)]),
            create_test_frame(0.0, [create_test_player("player1", 0)]),
            create_test_frame(0.0, [create_test_player("player1", 0)]),
        ]

        result = analyze_movement(frames, {}, player_id="player1")

        # Each frame should fall back to the default duration
        assert result["time_slow_s"] == pytest.approx(0.1, rel=1e-3)

    def test_team_analysis_aggregation(self):
        """Test team analysis aggregates all players correctly."""
        # Create players with different movement patterns
        players_frame1 = [
            create_test_player("player1", 0, velocity=Vec3(500.0, 0.0, 0.0)),  # Blue team
            create_test_player("player2", 0, velocity=Vec3(1500.0, 0.0, 0.0)),  # Blue team
            create_test_player("player3", 1, velocity=Vec3(2000.0, 0.0, 0.0)),  # Orange team
        ]
        
        players_frame2 = [
            create_test_player("player1", 0, velocity=Vec3(600.0, 0.0, 0.0)),
            create_test_player("player2", 0, velocity=Vec3(1600.0, 0.0, 0.0)),
            create_test_player("player3", 1, velocity=Vec3(2100.0, 0.0, 0.0)),
        ]
        
        frames = [
            create_test_frame(0.0, players_frame1),
            create_test_frame(1.0, players_frame2),
        ]
        
        result = analyze_movement(frames, {}, team="BLUE")
        
        # Should aggregate blue team players (player1 and player2)
        # Blue team has 2 players, so time metrics should be summed
        assert result["time_slow_s"] == 2.0  # player1 slow in both frames
        assert result["time_boost_speed_s"] == 2.0  # player2 contributes in each frame
        
        # Average speed should be average of the two blue players
        player1_avg = (500.0 + 600.0) / 2
        player2_avg = (1500.0 + 1600.0) / 2
        team_avg_uu_s = (player1_avg + player2_avg) / 2
        expected_team_avg_kph = _uu_s_to_kph(team_avg_uu_s)
        assert abs(result["avg_speed_kph"] - expected_team_avg_kph) < 0.01
    
    def test_no_matching_player_returns_zeros(self):
        """Test that analysis returns zeros when player not found in frames."""
        players = [
            create_test_player("player2", 0),  # Different player ID
        ]
        
        frames = [create_test_frame(0.0, players)]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Should return zeros since player1 not found
        assert result["avg_speed_kph"] == 0.0
        assert result["distance_km"] == 0.0
        assert result["max_speed_kph"] == 0.0
        assert result["time_ground_s"] == 0.0
        assert result["powerslide_count"] == 0
        assert result["aerial_count"] == 0
    
    def test_calculate_speed_utility(self):
        """Test speed calculation utility function."""
        # Test zero velocity
        assert _calculate_speed(Vec3(0.0, 0.0, 0.0)) == 0.0
        
        # Test simple cases
        assert _calculate_speed(Vec3(3.0, 4.0, 0.0)) == 5.0  # 3-4-5 triangle
        assert _calculate_speed(Vec3(1.0, 0.0, 0.0)) == 1.0
        
        # Test 3D case
        speed = _calculate_speed(Vec3(1.0, 1.0, 1.0))
        assert abs(speed - math.sqrt(3.0)) < 0.0001
    
    def test_uu_s_to_kph_conversion(self):
        """Test Unreal Units per second to km/h conversion."""
        # Test zero
        assert _uu_s_to_kph(0.0) == 0.0
        
        # Test known conversion (approximately 1 UU = 1.9 cm)
        # 1000 UU/s should be about 68.4 km/h
        result = _uu_s_to_kph(1000.0)
        assert 68.0 < result < 69.0
    
    def test_frame_duration_handling(self):
        """Test proper handling of variable frame durations."""
        players = [
            create_test_player("player1", 0, velocity=Vec3(1800.0, 0.0, 0.0)),
        ]
        
        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(0.5, [players[0]]),  # 0.5s duration
            create_test_frame(1.5, [players[0]]),  # 1.0s duration
        ]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Total time includes all frame durations (0.5s + 1.0s + 1.0s = 2.5s total)
        # All frames have boost speed velocity
        assert abs(result["time_boost_speed_s"] - 2.5) < 0.1
    
    def test_supersonic_flag_override(self):
        """Test that is_supersonic flag overrides speed calculation."""
        # Velocity below supersonic threshold but flag set
        players = [
            create_test_player("player1", 0, velocity=Vec3(1500.0, 0.0, 0.0), is_supersonic=True),
        ]
        
        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(1.0, [players[0]]),
        ]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Should classify as supersonic due to flag, not velocity
        assert result["time_supersonic_s"] == 2.0  # Both frames get 1s each
        assert result["time_boost_speed_s"] == 0.0
    
    def test_supersonic_hysteresis_handles_minor_dips(self):
        """Supersonic state should persist through small horizontal speed drops."""
        frames = [
            create_test_frame(0.0, [create_test_player("player1", 0, velocity=Vec3(2300.0, 0.0, 0.0))]),
            create_test_frame(1.0, [create_test_player("player1", 0, velocity=Vec3(2150.0, 0.0, 0.0))]),
            create_test_frame(2.0, [create_test_player("player1", 0, velocity=Vec3(2000.0, 0.0, 0.0))]),
        ]

        result = analyze_movement(frames, {}, player_id="player1")

        assert result["time_supersonic_s"] == pytest.approx(2.0, rel=1e-3)
        assert result["time_boost_speed_s"] == pytest.approx(1.0, rel=1e-3)
    
    def test_demolished_player_handling(self):
        """Test handling of demolished players in frames."""
        players = [
            create_test_player("player1", 0, velocity=Vec3(1800.0, 0.0, 0.0), is_demolished=False),
            create_test_player("player1", 0, velocity=Vec3(0.0, 0.0, 0.0), is_demolished=True),
        ]
        
        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(1.0, [players[1]]),  # Demolished
        ]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Should still process demolished player frames
        assert result["time_boost_speed_s"] == 1.0  # First frame
        assert result["time_slow_s"] == 1.0  # Second frame (0 velocity)
    
    def test_single_frame_analysis(self):
        """Test analysis with only one frame."""
        players = [
            create_test_player("player1", 0, velocity=Vec3(1000.0, 0.0, 0.0)),
        ]
        
        frames = [create_test_frame(0.0, [players[0]])]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Should handle single frame without errors
        assert result["avg_speed_kph"] > 0.0
        # Time metrics might be 0 due to no frame duration
        assert result["powerslide_count"] == 0  # Can't detect without previous frame
        assert result["aerial_count"] == 0
    
    def test_complex_movement_scenario(self):
        """Test complex scenario with multiple movement patterns."""
        players = [
            # Ground, slow
            create_test_player("player1", 0,
                               position=Vec3(0.0, 0.0, 17.0),
                               velocity=Vec3(300.0, 0.0, 0.0),
                               is_on_ground=True),
            # Ground, boost speed
            create_test_player("player1", 0,
                               position=Vec3(0.0, 0.0, 17.0),
                               velocity=Vec3(1800.0, 0.0, 0.0),
                               is_on_ground=True),
            # Air, supersonic
            create_test_player("player1", 0,
                               position=Vec3(0.0, 0.0, 300.0),
                               velocity=Vec3(2400.0, 0.0, 0.0),
                               is_supersonic=True,
                               is_on_ground=False),
            # High air, medium speed
            create_test_player("player1", 0,
                               position=Vec3(0.0, 0.0, 600.0),
                               velocity=Vec3(800.0, 0.0, 0.0),
                               is_on_ground=False),
        ]
        
        frames = [
            create_test_frame(0.0, [players[0]]),
            create_test_frame(1.0, [players[1]]),
            create_test_frame(2.0, [players[2]]),
            create_test_frame(3.0, [players[3]]),
        ]
        
        result = analyze_movement(frames, {}, player_id="player1")
        
        # Verify speed buckets
        assert result["time_slow_s"] == 2.0  # frames 0 and 3
        assert result["time_boost_speed_s"] == 1.0  # frame 1
        assert result["time_supersonic_s"] == 1.0  # frame 2
        
        # Verify height classifications
        assert result["time_ground_s"] == 2.0  # frames 0 and 1
        assert result["time_low_air_s"] == 1.0  # frame 2
        assert result["time_high_air_s"] == 1.0  # frame 3
        
        # Calculate expected average speed
        speeds = [300.0, 1800.0, 2400.0, 800.0]
        expected_avg_uu_s = sum(speeds) / len(speeds)
        expected_avg_kph = _uu_s_to_kph(expected_avg_uu_s)
        assert abs(result["avg_speed_kph"] - expected_avg_kph) < 0.01
