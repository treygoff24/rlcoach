"""Tests for positioning analysis."""

import math

from rlcoach.analysis.positioning import (
    _calculate_distance,
    analyze_positioning,
    calculate_rotation_compliance,
)
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame


def create_test_frame(timestamp: float, ball_pos: Vec3, players: list[PlayerFrame]) -> Frame:
    """Helper to create test frames with specific ball position."""
    return Frame(
        timestamp=timestamp,
        ball=BallFrame(
            position=ball_pos,
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


class TestPositioningAnalysis:
    """Test positioning analysis functions."""
    
    def test_empty_frames_returns_zeros(self):
        """Empty frames should return all zero metrics."""
        frames = []
        events = {}
        
        result = analyze_positioning(frames, events, player_id="player1")
        
        assert result["time_offensive_half_s"] == 0.0
        assert result["time_defensive_half_s"] == 0.0
        assert result["time_offensive_third_s"] == 0.0
        assert result["time_middle_third_s"] == 0.0
        assert result["time_defensive_third_s"] == 0.0
        assert result["behind_ball_pct"] == 0.0
        assert result["ahead_ball_pct"] == 0.0
        assert result["avg_distance_to_ball_m"] == 0.0
        assert result["avg_distance_to_teammate_m"] == 0.0
        assert result["first_man_pct"] == 0.0
        assert result["second_man_pct"] == 0.0
        # third_man_pct is None when team_size < 3 (empty frames = team_size 0)
        assert result["third_man_pct"] is None

    def test_field_half_classification_blue_team(self):
        """Test field half classification for blue team (team 0)."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            # Blue player in defensive half (negative Y)
            create_test_player("player1", 0, position=Vec3(0.0, -2000.0, 17.0)),
            # Blue player in offensive half (positive Y)
            create_test_player("player1", 0, position=Vec3(0.0, 2000.0, 17.0)),
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, [players[0]]),
            create_test_frame(1.0, ball_pos, [players[1]]),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # Blue team: negative Y = defensive, positive Y = offensive
        assert result["time_defensive_half_s"] == 1.0
        assert result["time_offensive_half_s"] == 1.0
    
    def test_field_half_classification_orange_team(self):
        """Test field half classification for orange team (team 1)."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            # Orange player in defensive half (positive Y)
            create_test_player("player2", 1, position=Vec3(0.0, 2000.0, 17.0)),
            # Orange player in offensive half (negative Y)
            create_test_player("player2", 1, position=Vec3(0.0, -2000.0, 17.0)),
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, [players[0]]),
            create_test_frame(1.0, ball_pos, [players[1]]),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player2")
        
        # Orange team: positive Y = defensive, negative Y = offensive
        assert result["time_defensive_half_s"] == 1.0
        assert result["time_offensive_half_s"] == 1.0
    
    def test_field_thirds_classification_blue_team(self):
        """Test field thirds classification for blue team."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        # Field thirds: defensive < -1706.67, neutral -1706.67 to 1706.67, offensive > 1706.67
        players = [
            # Blue defensive third
            create_test_player("player1", 0, position=Vec3(0.0, -3000.0, 17.0)),
            # Blue neutral third  
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 17.0)),
            # Blue offensive third
            create_test_player("player1", 0, position=Vec3(0.0, 3000.0, 17.0)),
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, [players[0]]),
            create_test_frame(1.0, ball_pos, [players[1]]),
            create_test_frame(2.0, ball_pos, [players[2]]),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        assert result["time_defensive_third_s"] == 1.0
        assert result["time_middle_third_s"] == 1.0  
        assert result["time_offensive_third_s"] == 1.0
    
    def test_field_thirds_classification_orange_team(self):
        """Test field thirds classification for orange team (flipped perspective)."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            # Orange in what's normally "defensive" third but is offensive for orange
            create_test_player("player2", 1, position=Vec3(0.0, -3000.0, 17.0)),
            # Orange in neutral third
            create_test_player("player2", 1, position=Vec3(0.0, 0.0, 17.0)),
            # Orange in what's normally "offensive" third but is defensive for orange
            create_test_player("player2", 1, position=Vec3(0.0, 3000.0, 17.0)),
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, [players[0]]),
            create_test_frame(1.0, ball_pos, [players[1]]),
            create_test_frame(2.0, ball_pos, [players[2]]),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player2")
        
        # Orange perspective is flipped
        assert result["time_offensive_third_s"] == 1.0  # Was defensive third
        assert result["time_middle_third_s"] == 1.0
        assert result["time_defensive_third_s"] == 1.0  # Was offensive third
    
    def test_behind_ahead_ball_calculation_blue_team(self):
        """Test behind/ahead ball percentage calculation for blue team."""
        players = [
            # Blue player behind ball (player Y < ball Y - threshold)
            create_test_player("player1", 0, position=Vec3(0.0, -200.0, 17.0)),
            # Blue player ahead of ball (player Y > ball Y + threshold)
            create_test_player("player1", 0, position=Vec3(0.0, 200.0, 17.0)),
            # Blue player roughly at ball position (within threshold)
            create_test_player("player1", 0, position=Vec3(0.0, 25.0, 17.0)),
        ]
        
        ball_pos = Vec3(0.0, 0.0, 93.15)  # Ball at center
        
        frames = [
            create_test_frame(0.0, ball_pos, [players[0]]),
            create_test_frame(1.0, ball_pos, [players[1]]),
            create_test_frame(2.0, ball_pos, [players[2]]),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # 1 behind, 1 ahead, 1 neutral = 33.33% each
        assert abs(result["behind_ball_pct"] - 33.33) < 0.1
        assert abs(result["ahead_ball_pct"] - 33.33) < 0.1
    
    def test_behind_ahead_ball_calculation_orange_team(self):
        """Test behind/ahead ball calculation for orange team (flipped)."""
        players = [
            # Orange player behind ball (player Y > ball Y + threshold)
            create_test_player("player2", 1, position=Vec3(0.0, 200.0, 17.0)),
            # Orange player ahead of ball (player Y < ball Y - threshold)
            create_test_player("player2", 1, position=Vec3(0.0, -200.0, 17.0)),
        ]
        
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        frames = [
            create_test_frame(0.0, ball_pos, [players[0]]),
            create_test_frame(1.0, ball_pos, [players[1]]),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player2")
        
        # Orange perspective is flipped
        assert result["behind_ball_pct"] == 50.0
        assert result["ahead_ball_pct"] == 50.0
    
    def test_distance_to_ball_calculation(self):
        """Test average distance to ball calculation."""
        ball_positions = [
            Vec3(0.0, 0.0, 93.15),
            Vec3(1000.0, 0.0, 93.15),
        ]
        
        player_positions = [
            Vec3(0.0, 0.0, 17.0),      # Distance = ~76 UU
            Vec3(0.0, 0.0, 17.0),      # Distance = ~1000 UU
        ]
        
        players = [
            create_test_player("player1", 0, position=player_positions[0]),
            create_test_player("player1", 0, position=player_positions[1]),
        ]
        
        frames = [
            create_test_frame(0.0, ball_positions[0], [players[0]]),
            create_test_frame(1.0, ball_positions[1], [players[1]]),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # Average distance should be roughly (76 + 1000) / 2 = 538 UU = 5.38 m
        expected_distance_m = 5.38
        assert abs(result["avg_distance_to_ball_m"] - expected_distance_m) < 1.0
    
    def test_role_detection_first_man(self):
        """Test first man role detection (closest to ball)."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            # Player 1 closest to ball
            create_test_player("player1", 0, position=Vec3(0.0, 500.0, 17.0)),
            # Teammates further away
            create_test_player("player2", 0, position=Vec3(0.0, 1500.0, 17.0)),
            create_test_player("player3", 0, position=Vec3(0.0, 2500.0, 17.0)),
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, players),
            create_test_frame(1.0, ball_pos, players),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # Player1 should be first man 100% of the time
        assert result["first_man_pct"] == 100.0
        assert result["second_man_pct"] == 0.0
        assert result["third_man_pct"] == 0.0
    
    def test_role_detection_second_man(self):
        """Test second man role detection."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            # Player 2 is second closest
            create_test_player("player1", 0, position=Vec3(0.0, 1500.0, 17.0)),  # Second closest
            create_test_player("player2", 0, position=Vec3(0.0, 500.0, 17.0)),   # Closest
            create_test_player("player3", 0, position=Vec3(0.0, 2500.0, 17.0)),  # Furthest
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, players),
            create_test_frame(1.0, ball_pos, players),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # Player1 should be second man 100% of the time
        assert result["first_man_pct"] == 0.0
        assert result["second_man_pct"] == 100.0
        assert result["third_man_pct"] == 0.0
    
    def test_role_detection_third_man(self):
        """Test third man role detection."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            # Player 3 is furthest from ball
            create_test_player("player1", 0, position=Vec3(0.0, 2500.0, 17.0)),  # Furthest
            create_test_player("player2", 0, position=Vec3(0.0, 500.0, 17.0)),   # Closest
            create_test_player("player3", 0, position=Vec3(0.0, 1500.0, 17.0)),  # Second
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, players),
            create_test_frame(1.0, ball_pos, players),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # Player1 should be third man 100% of the time
        assert result["first_man_pct"] == 0.0
        assert result["second_man_pct"] == 0.0
        assert result["third_man_pct"] == 100.0
    
    def test_distance_to_teammates_calculation(self):
        """Test average distance to teammates calculation."""
        players_frame1 = [
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 17.0)),
            create_test_player("player2", 0, position=Vec3(1000.0, 0.0, 17.0)),  # 1000 UU away
            create_test_player("player3", 0, position=Vec3(0.0, 1000.0, 17.0)),  # 1000 UU away
        ]
        
        players_frame2 = [
            create_test_player("player1", 0, position=Vec3(0.0, 0.0, 17.0)),
            create_test_player("player2", 0, position=Vec3(500.0, 0.0, 17.0)),   # 500 UU away
            create_test_player("player3", 0, position=Vec3(0.0, 500.0, 17.0)),   # 500 UU away
        ]
        
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        frames = [
            create_test_frame(0.0, ball_pos, players_frame1),
            create_test_frame(1.0, ball_pos, players_frame2),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # Frame 1: avg distance = 1000 UU, Frame 2: avg distance = 500 UU
        # Overall average = 750 UU = 7.5 m
        expected_distance_m = 7.5
        assert abs(result["avg_distance_to_teammate_m"] - expected_distance_m) < 0.5
    
    def test_team_analysis_aggregation(self):
        """Test team analysis aggregates all team players correctly."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            # Blue team players in different positions
            create_test_player("player1", 0, position=Vec3(0.0, -1000.0, 17.0)),  # Defensive
            create_test_player("player2", 0, position=Vec3(0.0, 1000.0, 17.0)),   # Offensive
            # Orange team player
            create_test_player("player3", 1, position=Vec3(0.0, 0.0, 17.0)),
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, players),
            create_test_frame(1.0, ball_pos, players),
        ]
        
        result = analyze_positioning(frames, {}, team="BLUE")
        
        # Team metrics should aggregate both blue players
        # Each player contributes 1s to their respective halves
        assert result["time_defensive_half_s"] == 2.0  # player1 in both frames
        assert result["time_offensive_half_s"] == 2.0  # player2 in both frames
        
        # Percentages should be averaged across team members
        # player1: 100% defensive half, player2: 100% offensive half
        # Team average should reflect this distribution
    
    def test_no_teammates_handling(self):
        """Test handling when player has no teammates (1v1 scenario)."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            create_test_player("player1", 0, position=Vec3(0.0, 1000.0, 17.0)),
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, players),
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")

        # Should handle gracefully without teammates
        assert result["avg_distance_to_teammate_m"] == 0.0
        assert result["first_man_pct"] == 100.0  # Only player, so always first man
        assert result["second_man_pct"] == 0.0
        # third_man_pct is None for 1v1 (team_size=1 < 3)
        assert result["third_man_pct"] is None

    def test_calculate_distance_utility(self):
        """Test distance calculation utility function."""
        # Test zero distance
        assert _calculate_distance(Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 0.0)) == 0.0
        
        # Test simple 2D case
        dist = _calculate_distance(Vec3(0.0, 0.0, 0.0), Vec3(3.0, 4.0, 0.0))
        assert abs(dist - 5.0) < 0.0001  # 3-4-5 triangle
        
        # Test 3D case
        dist = _calculate_distance(Vec3(0.0, 0.0, 0.0), Vec3(1.0, 1.0, 1.0))
        assert abs(dist - math.sqrt(3.0)) < 0.0001
    
    def test_rotation_compliance_double_commit_detection(self):
        """Test rotation compliance detects double commits."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        # Both players very close to ball (double commit scenario)
        players = [
            create_test_player("player1", 0, position=Vec3(100.0, 100.0, 17.0)),   # Close to ball
            create_test_player("player2", 0, position=Vec3(150.0, 150.0, 17.0)),   # Also close
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, players),
            create_test_frame(1.0, ball_pos, players),
            create_test_frame(2.0, ball_pos, players),
        ]
        
        result = calculate_rotation_compliance(frames, "player1")
        
        # Should detect double commit and lower score
        assert result["score_0_to_100"] < 90.0
        assert "double_commit" in result["flags"]
    
    def test_rotation_compliance_overcommit_detection(self):
        """Test rotation compliance detects last man overcommits."""
        ball_pos = Vec3(0.0, 1000.0, 93.15)  # Ball in offensive position
        
        # Blue team scenario - player1 is furthest back (last man) but goes forward with low boost
        players_frame1 = [
            create_test_player("player1", 0, position=Vec3(0.0, -2000.0, 17.0), boost_amount=10),  # Last man, low boost
            create_test_player("player2", 0, position=Vec3(0.0, 0.0, 17.0)),     # Forward
            create_test_player("player3", 0, position=Vec3(0.0, 500.0, 17.0)),   # Most forward
        ]
        
        # Player1 moves to offensive half with low boost but remains last man (overcommit)
        players_frame2 = [
            create_test_player("player1", 0, position=Vec3(0.0, 100.0, 17.0), boost_amount=5),   # Offensive half, low boost, but still last man
            create_test_player("player2", 0, position=Vec3(0.0, 200.0, 17.0)),  # More forward
            create_test_player("player3", 0, position=Vec3(0.0, 1000.0, 17.0)),  # Most forward
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, players_frame1),
            create_test_frame(1.0, ball_pos, players_frame2),
            create_test_frame(2.0, ball_pos, players_frame2),
        ]
        
        result = calculate_rotation_compliance(frames, "player1")
        
        # Should detect overcommit and include flag
        assert result["score_0_to_100"] < 95.0
        assert "last_man_overcommit" in result["flags"]
    
    def test_rotation_compliance_good_positioning(self):
        """Test rotation compliance with good positioning."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        # Well-spaced team with good positioning
        players = [
            create_test_player("player1", 0, position=Vec3(0.0, -1000.0, 17.0), boost_amount=50),  # Back
            create_test_player("player2", 0, position=Vec3(0.0, 0.0, 17.0), boost_amount=60),       # Mid
            create_test_player("player3", 0, position=Vec3(0.0, 800.0, 17.0), boost_amount=40),     # Forward
        ]
        
        frames = [
            create_test_frame(0.0, ball_pos, players),
            create_test_frame(1.0, ball_pos, players),
            create_test_frame(2.0, ball_pos, players),
        ]
        
        result = calculate_rotation_compliance(frames, "player1")
        
        # Should have high score with good positioning
        assert result["score_0_to_100"] >= 95.0
        assert len(result["flags"]) == 0  # No violations
    
    def test_complex_positioning_scenario(self):
        """Test complex positioning scenario with multiple metrics."""
        # Ball starts in center, moves around
        ball_positions = [
            Vec3(0.0, 0.0, 93.15),      # Center
            Vec3(0.0, 2000.0, 93.15),   # Orange side
            Vec3(0.0, -2000.0, 93.15),  # Blue side
        ]
        
        # Blue player moves from defensive to offensive
        players = [
            [create_test_player("player1", 0, position=Vec3(0.0, -3000.0, 17.0)),  # Defensive third
             create_test_player("player2", 0, position=Vec3(0.0, -1000.0, 17.0))],  # Teammate
            
            [create_test_player("player1", 0, position=Vec3(0.0, 0.0, 17.0)),       # Neutral third
             create_test_player("player2", 0, position=Vec3(0.0, 1000.0, 17.0))],
            
            [create_test_player("player1", 0, position=Vec3(0.0, 3000.0, 17.0)),    # Offensive third
             create_test_player("player2", 0, position=Vec3(0.0, 2000.0, 17.0))],
        ]
        
        frames = [
            create_test_frame(0.0, ball_positions[0], players[0]),
            create_test_frame(2.0, ball_positions[1], players[1]),  # 2s duration
            create_test_frame(3.0, ball_positions[2], players[2]),  # 1s duration
        ]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # Verify field third distribution 
        # Frame durations: 2s (defensive), 1s (neutral), 1s (offensive, estimated)
        assert result["time_defensive_third_s"] == 2.0
        assert result["time_middle_third_s"] == 1.0  
        assert result["time_offensive_third_s"] == 1.0  # Final frame gets estimated duration
        
        # Verify distance calculations include all frames
        assert result["avg_distance_to_ball_m"] > 0.0
        assert result["avg_distance_to_teammate_m"] > 0.0
    
    def test_player_not_found_in_frames(self):
        """Test handling when requested player is not in frames."""
        ball_pos = Vec3(0.0, 0.0, 93.15)
        
        players = [
            create_test_player("player2", 0),  # Different player
        ]
        
        frames = [create_test_frame(0.0, ball_pos, players)]
        
        result = analyze_positioning(frames, {}, player_id="player1")
        
        # Should return empty/zero results
        assert result["time_offensive_half_s"] == 0.0
        assert result["avg_distance_to_ball_m"] == 0.0
        assert result["first_man_pct"] == 0.0