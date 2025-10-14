"""Tests for boost analysis."""

import pytest
from unittest.mock import Mock

from rlcoach.analysis.boost import analyze_boost
from rlcoach.events import BoostPickupEvent
from rlcoach.field_constants import Vec3, FIELD
from rlcoach.parser.types import Header, Frame, PlayerFrame, BallFrame


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


def create_test_player(player_id: str, team: int, boost: int = 33, 
                      velocity: Vec3 = None, position: Vec3 = None) -> PlayerFrame:
    """Helper to create test player frames."""
    if velocity is None:
        velocity = Vec3(0.0, 0.0, 0.0)
    if position is None:
        position = Vec3(0.0, 0.0, 17.0)
        
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=position,
        velocity=velocity,
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=boost,
        is_supersonic=velocity and (velocity.x**2 + velocity.y**2 + velocity.z**2) > (2300**2),
        is_on_ground=True,
        is_demolished=False
    )


class TestBoostAnalysis:
    """Test boost analysis functions."""
    
    def test_empty_frames_returns_zeros(self):
        """Empty frames should return all zero metrics."""
        frames = []
        events = {}
        
        result = analyze_boost(frames, events, player_id="player1")
        
        assert result["bpm"] == 0.0
        assert result["bcpm"] == 0.0
        assert result["avg_boost"] == 0.0
        assert result["time_zero_boost_s"] == 0.0
        assert result["time_hundred_boost_s"] == 0.0
        assert result["amount_collected"] == 0.0
        assert result["amount_stolen"] == 0.0
        assert result["big_pads"] == 0
        assert result["small_pads"] == 0
        assert result["stolen_big_pads"] == 0
        assert result["stolen_small_pads"] == 0
        assert result["overfill"] == 0.0
        assert result["waste"] == 0.0
    
    def test_basic_boost_collection_tracking(self):
        """Test basic boost collection from pickup events."""
        player1 = create_test_player("player1", 0, boost=50)
        frames = [
            create_test_frame(0.0, [player1]),
            create_test_frame(60.0, [player1]),  # 60 second match
        ]
        
        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
                BoostPickupEvent(
                    t=20.0,
                    player_id="player1",
                    pad_type="SMALL",
                    stolen=False,
                    pad_id=5,
                    location=Vec3(0, 2048, 73),
                    boost_before=50.0,
                    boost_after=62.0,
                    boost_gain=12.0,
                ),
                BoostPickupEvent(
                    t=30.0,
                    player_id="player2",
                    pad_type="BIG",
                    stolen=True,
                    pad_id=1,
                    location=Vec3(-3584, 0, 73),
                    boost_before=10.0,
                    boost_after=100.0,
                    boost_gain=90.0,
                ),
            ]
        }
        
        result = analyze_boost(frames, events, player_id="player1")
        
        assert result["amount_collected"] == 112.0  # 100 (big) + 12 (small)
        assert result["amount_stolen"] == 0.0  # Neither pickup was stolen
        assert result["big_pads"] == 1
        assert result["small_pads"] == 1
        assert result["stolen_big_pads"] == 0
        assert result["stolen_small_pads"] == 0
        assert result["bpm"] == 112.0  # 112 boost in 1 minute
        assert result["bcpm"] == 2.0   # 2 pickups in 1 minute
    
    def test_stolen_boost_tracking(self):
        """Test tracking stolen boost pickups."""
        player1 = create_test_player("player1", 0)  # Blue team
        frames = [
            create_test_frame(0.0, [player1]),
            create_test_frame(60.0, [player1]),
        ]
        
        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=True,
                    pad_id=0,
                    location=Vec3(3584, 2500, 73),
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),  # Orange side
                BoostPickupEvent(
                    t=20.0,
                    player_id="player1",
                    pad_type="SMALL",
                    stolen=True,
                    pad_id=5,
                    location=Vec3(0, 3000, 73),
                    boost_before=10.0,
                    boost_after=22.0,
                    boost_gain=12.0,
                ),  # Orange side
                BoostPickupEvent(
                    t=30.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=1,
                    location=Vec3(-3584, -2500, 73),
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),  # Blue side
            ]
        }
        
        result = analyze_boost(frames, events, player_id="player1")
        
        assert result["amount_collected"] == 212.0  # 200 (2 big) + 12 (1 small)
        assert result["amount_stolen"] == 112.0    # 100 (1 big) + 12 (1 small)
        assert result["big_pads"] == 2
        assert result["small_pads"] == 1
        assert result["stolen_big_pads"] == 1
        assert result["stolen_small_pads"] == 1
    
    def test_time_at_zero_and_full_boost(self):
        """Test tracking time spent at 0 and 100 boost."""
        frames = [
            create_test_frame(0.0, [create_test_player("player1", 0, boost=2)]),   # Zero boost
            create_test_frame(10.0, [create_test_player("player1", 0, boost=1)]),  # Still zero
            create_test_frame(20.0, [create_test_player("player1", 0, boost=50)]), # Normal
            create_test_frame(30.0, [create_test_player("player1", 0, boost=99)]), # Full
            create_test_frame(40.0, [create_test_player("player1", 0, boost=100)]), # Still full
            create_test_frame(50.0, [create_test_player("player1", 0, boost=100)]), # Max full
            create_test_frame(60.0, [create_test_player("player1", 0, boost=30)]),  # Normal
        ]
        
        events = {}
        
        result = analyze_boost(frames, events, player_id="player1")
        
        assert result["time_zero_boost_s"] == 20.0   # 0-20s at zero boost  
        assert result["time_hundred_boost_s"] == 30.0 # 30-60s at full boost
        assert abs(result["avg_boost"] - 54.57) < 0.1  # Average of all boost amounts (allow small rounding)
    
    def test_overfill_detection(self):
        """Test overfill calculation when collecting boost above threshold."""
        # Create frames showing player with high boost before pickups
        frames = [
            create_test_frame(0.0, [create_test_player("player1", 0, boost=85)]),  # High boost
            create_test_frame(10.0, [create_test_player("player1", 0, boost=95)]), # Very high
            create_test_frame(20.0, [create_test_player("player1", 0, boost=50)]),
            create_test_frame(30.0, [create_test_player("player1", 0, boost=50)]),
        ]
        
        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    boost_before=85.0,
                    boost_after=100.0,
                    boost_gain=15.0,
                ),
                BoostPickupEvent(
                    t=20.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=1,
                    location=Vec3(-3584, 0, 73),
                    boost_before=95.0,
                    boost_after=100.0,
                    boost_gain=5.0,
                ),
                BoostPickupEvent(
                    t=30.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=2,
                    location=Vec3(0, 5120, 73),
                    boost_before=20.0,
                    boost_after=100.0,
                    boost_gain=80.0,
                ),
            ]
        }
        
        result = analyze_boost(frames, events, player_id="player1")
        
        assert result["overfill"] == 180.0  # 85 wasted + 95 wasted on two big-pad pickups
    
    def test_boost_waste_detection(self):
        """Test boost waste detection during supersonic speeds."""
        frames = [
            # Player using boost while supersonic (wasteful)
            create_test_frame(0.0, [create_test_player("player1", 0, boost=100, 
                                   velocity=Vec3(2400, 0, 0))]), # Supersonic
            create_test_frame(5.0, [create_test_player("player1", 0, boost=80,
                                   velocity=Vec3(2400, 0, 0))]),  # Still supersonic, used 20 boost
            # Player using boost effectively
            create_test_frame(10.0, [create_test_player("player1", 0, boost=70,
                                    velocity=Vec3(1500, 0, 0))]), # Not supersonic
            create_test_frame(15.0, [create_test_player("player1", 0, boost=60,
                                    velocity=Vec3(1800, 0, 0))]), # Accelerating
        ]
        
        events = {}
        
        result = analyze_boost(frames, events, player_id="player1")
        
        assert result["waste"] > 0.0  # Should detect some waste from supersonic boosting
    
    def test_bpm_and_bcpm_calculation(self):
        """Test BPM and BCPM rate calculations."""
        player1 = create_test_player("player1", 0)
        frames = [
            create_test_frame(0.0, [player1]),
            create_test_frame(120.0, [player1]),  # 2 minute match
        ]
        
        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=30.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
                BoostPickupEvent(
                    t=60.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=1,
                    location=Vec3(-3584, 0, 73),
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
                BoostPickupEvent(
                    t=90.0,
                    player_id="player1",
                    pad_type="SMALL",
                    stolen=False,
                    pad_id=5,
                    location=Vec3(0, 2048, 73),
                    boost_before=40.0,
                    boost_after=52.0,
                    boost_gain=12.0,
                ),
            ]
        }
        
        result = analyze_boost(frames, events, player_id="player1")
        
        # 212 boost collected in 2 minutes = 106 BPM
        assert result["bpm"] == 106.0
        # 3 pickups in 2 minutes = 1.5 BCPM
        assert result["bcpm"] == 1.5
        assert result["amount_collected"] == 212.0
    
    def test_team_analysis_aggregation(self):
        """Test team-level boost analysis aggregation."""
        player1 = create_test_player("player1", 0, boost=50)  # Blue team
        player2 = create_test_player("player2", 0, boost=30)  # Blue team
        player3 = create_test_player("player3", 1, boost=80)  # Orange team
        
        frames = [
            create_test_frame(0.0, [player1, player2, player3]),
            create_test_frame(60.0, [player1, player2, player3]),
        ]
        
        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
                BoostPickupEvent(
                    t=20.0,
                    player_id="player2",
                    pad_type="SMALL",
                    stolen=False,
                    pad_id=5,
                    location=Vec3(0, 2048, 73),
                    boost_before=30.0,
                    boost_after=42.0,
                    boost_gain=12.0,
                ),
                BoostPickupEvent(
                    t=30.0,
                    player_id="player3",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=1,
                    location=Vec3(-3584, 0, 73),
                    boost_before=20.0,
                    boost_after=100.0,
                    boost_gain=80.0,
                ),
            ]
        }
        
        result = analyze_boost(frames, events, team="BLUE")
        
        # Blue team collected: 100 (player1) + 12 (player2) = 112
        assert result["amount_collected"] == 112.0
        assert result["big_pads"] == 1      # player1's big pad
        assert result["small_pads"] == 1    # player2's small pad
        assert result["bpm"] == 112.0       # 112 in 1 minute
        assert result["bcpm"] == 2.0        # 2 pickups in 1 minute
        assert result["avg_boost"] == 40.0  # (50 + 30) / 2 players
    
    def test_no_pickup_events(self):
        """Test handling when no boost pickup events are available."""
        player1 = create_test_player("player1", 0, boost=50)
        frames = [
            create_test_frame(0.0, [player1]),
            create_test_frame(60.0, [player1]),
        ]
        
        events = {}  # No boost_pickups key
        
        result = analyze_boost(frames, events, player_id="player1")
        
        assert result["amount_collected"] == 0.0
        assert result["big_pads"] == 0
        assert result["small_pads"] == 0
        assert result["bpm"] == 0.0
        assert result["bcpm"] == 0.0
        assert result["avg_boost"] == 50.0  # Still calculated from frames
    
    def test_player_not_in_frames(self):
        """Test handling when requested player is not found in frames."""
        player2 = create_test_player("player2", 0)
        frames = [
            create_test_frame(0.0, [player2]),  # Only player2, not player1
            create_test_frame(60.0, [player2]),
        ]
        
        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
            ]
        }
        
        result = analyze_boost(frames, events, player_id="player1")
        
        # Player1 not in frames, so frame-based metrics should be zero
        assert result["avg_boost"] == 0.0
        assert result["time_zero_boost_s"] == 0.0
        assert result["time_hundred_boost_s"] == 0.0
        # But pickup-based metrics should still work
        assert result["amount_collected"] == 100.0
        assert result["big_pads"] == 1
    
    def test_header_only_mode(self):
        """Test graceful degradation with no frame data."""
        frames = []
        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
            ]
        }
        header = Mock()
        
        result = analyze_boost(frames, events, player_id="player1", header=header)
        
        # Should handle empty frames gracefully
        assert result["avg_boost"] == 0.0
        assert result["time_zero_boost_s"] == 0.0  
        assert result["time_hundred_boost_s"] == 0.0
        # Pickup data should still be processed
        assert result["amount_collected"] == 100.0
        assert result["bpm"] == 100.0  # 100 boost collected in default 1 minute duration
