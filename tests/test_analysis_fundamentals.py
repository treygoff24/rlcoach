"""Tests for fundamentals analysis."""

from unittest.mock import Mock

from rlcoach.analysis.fundamentals import analyze_fundamentals
from rlcoach.events import DemoEvent, GoalEvent, TouchEvent
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


def create_test_player(player_id: str, team: int) -> PlayerFrame:
    """Helper to create test player frames."""
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=Vec3(0.0, 0.0, 17.0),
        velocity=Vec3(0.0, 0.0, 0.0),
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=33,
        is_supersonic=False,
        is_on_ground=True,
        is_demolished=False
    )


class TestFundamentalsAnalysis:
    """Test fundamentals analysis functions."""
    
    def test_empty_events_returns_zeros(self):
        """Empty events should return all zero metrics."""
        frames = [create_test_frame(0.0, [])]
        events = {}
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["goals"] == 0
        assert result["assists"] == 0
        assert result["shots"] == 0
        assert result["saves"] == 0
        assert result["demos_inflicted"] == 0
        assert result["demos_taken"] == 0
        assert result["score"] == 0
        assert result["shooting_percentage"] == 0.0
    
    def test_player_goal_counting(self):
        """Test counting goals for specific player."""
        frames = []
        events = {
            "goals": [
                GoalEvent(t=10.0, scorer="player1", team="BLUE", shot_speed_kph=80.0, distance_m=5.0),
                GoalEvent(t=20.0, scorer="player2", team="ORANGE", shot_speed_kph=90.0, distance_m=3.0),
                GoalEvent(t=30.0, scorer="player1", team="BLUE", shot_speed_kph=70.0, distance_m=4.0),
            ]
        }
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["goals"] == 2
        assert result["assists"] == 0
        assert result["score"] == 200  # 2 goals * 100 points each
    
    def test_player_assist_counting(self):
        """Test counting assists for specific player.""" 
        frames = []
        events = {
            "goals": [
                GoalEvent(t=10.0, scorer="player1", assist="player2", team="BLUE", shot_speed_kph=80.0, distance_m=5.0),
                GoalEvent(t=20.0, scorer="player2", assist="player1", team="BLUE", shot_speed_kph=90.0, distance_m=3.0),
                GoalEvent(t=30.0, scorer="player3", assist="player4", team="ORANGE", shot_speed_kph=70.0, distance_m=4.0),
            ]
        }
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["goals"] == 1
        assert result["assists"] == 1
        assert result["score"] == 150  # 100 (goal) + 50 (assist)
    
    def test_demo_counting(self):
        """Test counting demos inflicted and taken."""
        frames = []
        events = {
            "demos": [
                DemoEvent(t=10.0, victim="player1", attacker="player2", 
                         team_victim="BLUE", team_attacker="ORANGE", 
                         location=Vec3(0.0, 0.0, 17.0)),
                DemoEvent(t=20.0, victim="player3", attacker="player1",
                         team_victim="ORANGE", team_attacker="BLUE",
                         location=Vec3(0.0, 0.0, 17.0)),
                DemoEvent(t=30.0, victim="player4", attacker="player2",
                         team_victim="ORANGE", team_attacker="ORANGE", 
                         location=Vec3(0.0, 0.0, 17.0)),
            ]
        }
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["demos_inflicted"] == 1
        assert result["demos_taken"] == 1
        assert result["score"] == 25  # 1 demo inflicted * 25 points
    
    def test_shot_and_save_counting_from_touches(self):
        """Test counting shots and saves from touch events."""
        frames = []
        events = {
            "goals": [
                # Need goals for team inference
                GoalEvent(t=5.0, scorer="player1", team="BLUE", shot_speed_kph=80.0, distance_m=5.0),
            ],
            "touches": [
                TouchEvent(t=10.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=100.0, outcome="SHOT"),
                TouchEvent(t=15.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=80.0, outcome="SHOT"),
                TouchEvent(t=20.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=60.0, outcome="SAVE"),
                TouchEvent(t=25.0, player_id="player2", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=90.0, outcome="SHOT"),
            ]
        }
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["shots"] == 2
        assert result["saves"] == 1
        assert result["goals"] == 1
        assert result["score"] == 215  # 100 (goal) + 40 (2 shots) + 75 (save)
    
    def test_shooting_percentage_calculation(self):
        """Test shooting percentage calculation."""
        frames = []
        events = {
            "goals": [
                GoalEvent(t=10.0, scorer="player1", team="BLUE", shot_speed_kph=80.0, distance_m=5.0),
                GoalEvent(t=20.0, scorer="player1", team="BLUE", shot_speed_kph=90.0, distance_m=3.0),
            ],
            "touches": [
                TouchEvent(t=15.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=100.0, outcome="SHOT"),
                TouchEvent(t=25.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=80.0, outcome="SHOT"),
                TouchEvent(t=35.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=75.0, outcome="SHOT"),
                TouchEvent(t=45.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=70.0, outcome="SHOT"),
                TouchEvent(t=55.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=65.0, outcome="SHOT"),
            ]
        }
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["goals"] == 2
        assert result["shots"] == 5
        assert result["shooting_percentage"] == 40.0  # 2 goals / 5 shots = 40%
    
    def test_zero_shots_shooting_percentage(self):
        """Test shooting percentage when no shots taken."""
        frames = []
        events = {
            "goals": [
                GoalEvent(t=10.0, scorer="player1", team="BLUE", shot_speed_kph=80.0, distance_m=5.0),
            ]
        }
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["goals"] == 1
        assert result["shots"] == 0
        assert result["shooting_percentage"] == 0.0
    
    def test_team_analysis(self):
        """Test team-level analysis aggregation."""
        frames = []
        events = {
            "goals": [
                GoalEvent(t=10.0, scorer="player1", team="BLUE", shot_speed_kph=80.0, distance_m=5.0),
                GoalEvent(t=20.0, scorer="player2", team="BLUE", shot_speed_kph=90.0, distance_m=3.0),
                GoalEvent(t=30.0, scorer="player3", team="ORANGE", shot_speed_kph=70.0, distance_m=4.0),
            ],
            "demos": [
                DemoEvent(t=15.0, victim="player3", attacker="player1",
                         team_victim="ORANGE", team_attacker="BLUE",
                         location=Vec3(0.0, 0.0, 17.0)),
            ]
        }
        
        result = analyze_fundamentals(frames, events, team="BLUE")
        
        assert result["goals"] == 2  # player1 and player2 goals
        assert result["demos_inflicted"] == 1  # player1 demo
        assert result["score"] == 225  # 200 (goals) + 25 (demo)
    
    def test_header_only_mode(self):
        """Test graceful handling of missing event data."""
        frames = []  # No frames
        events = {}  # No events
        header = Mock()
        
        result = analyze_fundamentals(frames, events, player_id="player1", header=header)
        
        # Should return zeros without errors
        assert result["goals"] == 0
        assert result["assists"] == 0
        assert result["shots"] == 0
        assert result["saves"] == 0
        assert result["demos_inflicted"] == 0
        assert result["demos_taken"] == 0
        assert result["score"] == 0
        assert result["shooting_percentage"] == 0.0
    
    def test_missing_event_categories(self):
        """Test handling missing event categories gracefully."""
        frames = []
        events = {
            "goals": [
                GoalEvent(t=10.0, scorer="player1", team="BLUE", shot_speed_kph=80.0, distance_m=5.0),
            ]
            # Missing 'demos' and 'touches' keys
        }
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["goals"] == 1
        assert result["assists"] == 0
        assert result["shots"] == 0  # No touches events
        assert result["saves"] == 0  # No touches events
        assert result["demos_inflicted"] == 0  # No demos events
        assert result["demos_taken"] == 0  # No demos events
        assert result["score"] == 100  # Only goal score
    
    def test_complex_scoring_scenario(self):
        """Test complex scoring with multiple event types."""
        frames = []
        events = {
            "goals": [
                GoalEvent(t=10.0, scorer="player1", assist="player2", team="BLUE", 
                         shot_speed_kph=80.0, distance_m=5.0),
                GoalEvent(t=30.0, scorer="player1", team="BLUE", shot_speed_kph=90.0, distance_m=3.0),
            ],
            "demos": [
                DemoEvent(t=20.0, victim="player3", attacker="player1",
                         team_victim="ORANGE", team_attacker="BLUE",
                         location=Vec3(0.0, 0.0, 17.0)),
                DemoEvent(t=40.0, victim="player1", attacker="player4", 
                         team_victim="BLUE", team_attacker="ORANGE",
                         location=Vec3(0.0, 0.0, 17.0)),
            ],
            "touches": [
                TouchEvent(t=15.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=100.0, outcome="SHOT"),
                TouchEvent(t=25.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=80.0, outcome="SHOT"),
                TouchEvent(t=35.0, player_id="player1", location=Vec3(0.0, 0.0, 17.0),
                          ball_speed_kph=60.0, outcome="SAVE"),
            ]
        }
        
        result = analyze_fundamentals(frames, events, player_id="player1")
        
        assert result["goals"] == 2
        assert result["assists"] == 0  # Assists are separate from goals
        assert result["shots"] == 2 
        assert result["saves"] == 1
        assert result["demos_inflicted"] == 1
        assert result["demos_taken"] == 1
        assert result["shooting_percentage"] == 100.0  # 2 goals / 2 shots
        
        # Score calculation: 2*100 (goals) + 2*20 (shots) + 1*75 (save) + 1*25 (demo inflicted)
        expected_score = 200 + 40 + 75 + 25
        assert result["score"] == expected_score