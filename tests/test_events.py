"""Tests for event detection and timeline aggregation."""

import pytest
from unittest.mock import Mock

from rlcoach.events import (
    detect_goals, detect_demos, detect_kickoffs, detect_boost_pickups, 
    detect_touches, build_timeline,
    GoalEvent, DemoEvent, KickoffEvent, BoostPickupEvent, TouchEvent, TimelineEvent,
    GOAL_LINE_THRESHOLD, TOUCH_PROXIMITY_THRESHOLD, BOOST_PAD_PROXIMITY_THRESHOLD
)
from rlcoach.field_constants import Vec3, FIELD
from rlcoach.parser.types import Header, PlayerInfo, Frame, PlayerFrame, BallFrame


def create_test_frame(timestamp: float, ball_pos: Vec3, ball_vel: Vec3, players: list[PlayerFrame]) -> Frame:
    """Helper to create test frames."""
    return Frame(
        timestamp=timestamp,
        ball=BallFrame(
            position=ball_pos,
            velocity=ball_vel,
            angular_velocity=Vec3(0.0, 0.0, 0.0)
        ),
        players=players
    )


def create_test_player(player_id: str, team: int, pos: Vec3, boost: int = 33, 
                      demolished: bool = False, on_ground: bool = True) -> PlayerFrame:
    """Helper to create test player frames."""
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=pos,
        velocity=Vec3(0.0, 0.0, 0.0),
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=boost,
        is_supersonic=False,
        is_on_ground=on_ground,
        is_demolished=demolished
    )


class TestGoalDetection:
    """Test goal event detection."""
    
    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no goals."""
        goals = detect_goals([])
        assert goals == []
    
    def test_blue_team_goal(self):
        """Blue team scoring in orange goal (positive Y)."""
        # Ball approaching orange goal
        frames = [
            create_test_frame(
                1.0, 
                Vec3(0.0, 4800.0, 100.0),  # Well before goal line
                Vec3(0.0, 500.0, 0.0),     # Moving toward goal
                [create_test_player("player_1", 0, Vec3(0.0, 4700.0, 17.0))]  # Blue player near ball
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 5200.0, 100.0),  # Ball crosses goal line
                Vec3(0.0, 500.0, 0.0),
                [create_test_player("player_1", 0, Vec3(0.0, 4900.0, 17.0))]
            )
        ]
        
        goals = detect_goals(frames)
        assert len(goals) == 1
        
        goal = goals[0]
        assert goal.t == 1.1
        assert goal.scorer == "player_1"
        assert goal.team == "BLUE"
        assert goal.shot_speed_kph > 0
    
    def test_orange_team_goal(self):
        """Orange team scoring in blue goal (negative Y)."""
        frames = [
            create_test_frame(
                2.0,
                Vec3(0.0, -4800.0, 100.0),  # Well before blue goal
                Vec3(0.0, -500.0, 0.0),     # Moving toward goal
                [create_test_player("player_2", 1, Vec3(0.0, -4700.0, 17.0))]  # Orange player near ball
            ),
            create_test_frame(
                2.1,
                Vec3(0.0, -5200.0, 100.0),  # Ball crosses goal line
                Vec3(0.0, -500.0, 0.0),
                [create_test_player("player_2", 1, Vec3(0.0, -4900.0, 17.0))]
            )
        ]
        
        goals = detect_goals(frames)
        assert len(goals) == 1
        
        goal = goals[0]
        assert goal.team == "ORANGE"
        assert goal.scorer == "player_2"
    
    def test_no_recent_touch_no_scorer(self):
        """Goal without recent player touch has no scorer."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 5200.0, 100.0),  # Ball already past goal line
                Vec3(0.0, 100.0, 0.0),
                []  # No players near ball
            )
        ]
        
        goals = detect_goals(frames)
        assert len(goals) == 1
        assert goals[0].scorer is None
    
    def test_ball_not_crossing_goal_line(self):
        """Ball staying in field doesn't trigger goal."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 4000.0, 100.0),  # Ball in field
                Vec3(0.0, 100.0, 0.0),
                [create_test_player("player_1", 0, Vec3(0.0, 3800.0, 17.0))]
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 4500.0, 100.0),  # Still in field
                Vec3(0.0, 100.0, 0.0),
                [create_test_player("player_1", 0, Vec3(0.0, 4300.0, 17.0))]
            )
        ]
        
        goals = detect_goals(frames)
        assert goals == []


class TestDemoDetection:
    """Test demolition event detection."""
    
    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no demos."""
        demos = detect_demos([])
        assert demos == []
    
    def test_player_gets_demolished(self):
        """Player state transition from alive to demolished."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("victim", 0, Vec3(1000.0, 0.0, 17.0), demolished=False),
                    create_test_player("attacker", 1, Vec3(1100.0, 0.0, 17.0), demolished=False)
                ]
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("victim", 0, Vec3(1000.0, 0.0, 17.0), demolished=True),
                    create_test_player("attacker", 1, Vec3(1050.0, 0.0, 17.0), demolished=False)
                ]
            )
        ]
        
        demos = detect_demos(frames)
        assert len(demos) == 1
        
        demo = demos[0]
        assert demo.t == 1.1
        assert demo.victim == "victim"
        assert demo.attacker == "attacker"
        assert demo.team_victim == "BLUE"
        assert demo.team_attacker == "ORANGE"
    
    def test_no_demo_transition_no_event(self):
        """No state change means no demo event."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("player_1", 0, Vec3(1000.0, 0.0, 17.0), demolished=False)]
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("player_1", 0, Vec3(1100.0, 0.0, 17.0), demolished=False)]
            )
        ]
        
        demos = detect_demos(frames)
        assert demos == []
    
    def test_demo_without_nearby_attacker(self):
        """Demo event with no clear attacker nearby."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("victim", 0, Vec3(1000.0, 0.0, 17.0), demolished=False),
                    create_test_player("far_player", 1, Vec3(3000.0, 0.0, 17.0), demolished=False)  # Too far
                ]
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("victim", 0, Vec3(1000.0, 0.0, 17.0), demolished=True),
                    create_test_player("far_player", 1, Vec3(3000.0, 0.0, 17.0), demolished=False)
                ]
            )
        ]
        
        demos = detect_demos(frames)
        assert len(demos) == 1
        assert demos[0].attacker is None


class TestKickoffDetection:
    """Test kickoff event detection."""
    
    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no kickoffs."""
        kickoffs = detect_kickoffs([])
        assert kickoffs == []
    
    def test_initial_kickoff_detected(self):
        """Ball at center triggers kickoff detection."""
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, 0.0, 93.15),    # Ball at center
                Vec3(0.0, 0.0, 0.0),      # Stationary
                [
                    create_test_player("p1", 0, Vec3(-500.0, -1000.0, 17.0)),  # Blue side
                    create_test_player("p2", 1, Vec3(500.0, 1000.0, 17.0))     # Orange side
                ]
            ),
            create_test_frame(
                0.5,
                Vec3(0.0, 0.0, 93.15),    # Still at center
                Vec3(0.0, 0.0, 0.0),      # Still stationary
                [
                    create_test_player("p1", 0, Vec3(-200.0, -800.0, 17.0)),
                    create_test_player("p2", 1, Vec3(200.0, 800.0, 17.0))
                ]
            ),
            create_test_frame(
                1.0,
                Vec3(100.0, 200.0, 100.0),  # Ball moves away
                Vec3(200.0, 400.0, 50.0),   # Ball has velocity
                [
                    create_test_player("p1", 0, Vec3(50.0, -50.0, 17.0)),
                    create_test_player("p2", 1, Vec3(150.0, 150.0, 17.0))
                ]
            )
        ]
        
        kickoffs = detect_kickoffs(frames)
        assert len(kickoffs) == 1
        
        kickoff = kickoffs[0]
        assert kickoff.phase == "INITIAL"
        assert kickoff.t_start == 0.0
        assert len(kickoff.players) == 2
    
    def test_overtime_kickoff(self):
        """Late-game kickoff detected as overtime."""
        frames = [
            create_test_frame(
                350.0,  # Late in match
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(-200.0, -200.0, 17.0))]
            ),
            create_test_frame(
                351.0,
                Vec3(200.0, 300.0, 150.0),  # Ball moves
                Vec3(400.0, 600.0, 100.0),
                [create_test_player("p1", 0, Vec3(100.0, 100.0, 17.0))]
            )
        ]
        
        kickoffs = detect_kickoffs(frames)
        assert len(kickoffs) == 1
        assert kickoffs[0].phase == "OT"
    
    def test_ball_not_at_center_no_kickoff(self):
        """Ball away from center doesn't trigger kickoff."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),  # Ball away from center
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(500.0, 1000.0, 17.0))]
            )
        ]
        
        kickoffs = detect_kickoffs(frames)
        assert kickoffs == []


class TestBoostPickupDetection:
    """Test boost pickup event detection."""
    
    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no pickups."""
        pickups = detect_boost_pickups([])
        assert pickups == []
    
    def test_big_boost_pickup(self):
        """Large boost increase detected as big pad pickup."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(-3584.0, -4240.0, 17.0), boost=20)]  # Near corner boost
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(-3584.0, -4240.0, 17.0), boost=100)]  # Got 100 boost
            )
        ]
        
        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1
        
        pickup = pickups[0]
        assert pickup.t == 1.1
        assert pickup.player_id == "p1"
        assert pickup.pad_type == "BIG"
        assert pickup.stolen is False  # Blue player in blue corner
    
    def test_small_boost_pickup(self):
        """Small boost increase detected as small pad pickup."""
        frames = [
            create_test_frame(
                2.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(1788.0, 0.0, 17.0), boost=50)]  # Near mid boost
            ),
            create_test_frame(
                2.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(1788.0, 0.0, 17.0), boost=62)]  # Got 12 boost
            )
        ]
        
        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1
        
        pickup = pickups[0]
        assert pickup.pad_type == "SMALL"
    
    def test_stolen_boost_detection(self):
        """Boost pickup on opponent half detected as stolen."""
        frames = [
            create_test_frame(
                3.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("blue_p", 0, Vec3(3584.0, 4240.0, 17.0), boost=10)]  # Blue in orange corner
            ),
            create_test_frame(
                3.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("blue_p", 0, Vec3(3584.0, 4240.0, 17.0), boost=100)]  # Boost stolen
            )
        ]
        
        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1
        assert pickups[0].stolen is True
    
    def test_no_boost_increase_no_pickup(self):
        """No boost change means no pickup event."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(1000.0, 0.0, 17.0), boost=50)]
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(1100.0, 0.0, 17.0), boost=50)]  # Same boost
            )
        ]
        
        pickups = detect_boost_pickups(frames)
        assert pickups == []


class TestTouchDetection:
    """Test player-ball touch detection."""
    
    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no touches."""
        touches = detect_touches([])
        assert touches == []
    
    def test_player_near_ball_creates_touch(self):
        """Player within proximity threshold creates touch event."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),  # Ball position
                Vec3(500.0, 0.0, 0.0),        # Ball moving
                [create_test_player("p1", 0, Vec3(1100.0, 2000.0, 17.0))]  # Player near ball
            )
        ]
        
        touches = detect_touches(frames)
        assert len(touches) == 1
        
        touch = touches[0]
        assert touch.t == 1.0
        assert touch.player_id == "p1"
        assert touch.ball_speed_kph > 0
    
    def test_high_speed_classified_as_shot(self):
        """High ball speed classified as shot."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),
                Vec3(2000.0, 0.0, 0.0),  # High speed
                [create_test_player("p1", 0, Vec3(1100.0, 2000.0, 17.0))]
            )
        ]
        
        touches = detect_touches(frames)
        assert len(touches) == 1
        assert touches[0].outcome == "SHOT"
    
    def test_low_speed_classified_as_dribble(self):
        """Low ball speed classified as dribble."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),
                Vec3(100.0, 0.0, 0.0),  # Low speed
                [create_test_player("p1", 0, Vec3(1100.0, 2000.0, 17.0))]
            )
        ]
        
        touches = detect_touches(frames)
        assert len(touches) == 1
        assert touches[0].outcome == "DRIBBLE"
    
    def test_player_far_from_ball_no_touch(self):
        """Player far from ball doesn't create touch event."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),  # Ball position
                Vec3(500.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(2000.0, 3000.0, 17.0))]  # Player far away
            )
        ]
        
        touches = detect_touches(frames)
        assert touches == []


class TestTimelineAggregation:
    """Test timeline building from events."""
    
    def test_empty_events_returns_empty_timeline(self):
        """Empty events dict returns empty timeline."""
        timeline = build_timeline({})
        assert timeline == []
    
    def test_mixed_events_sorted_chronologically(self):
        """Mixed event types sorted by timestamp."""
        goal = GoalEvent(t=2.0, scorer="p1", team="BLUE")
        demo = DemoEvent(t=1.0, victim="p2", attacker="p1")
        touch = TouchEvent(t=3.0, player_id="p1", location=Vec3(0.0, 0.0, 0.0))
        
        events = {
            'goals': [goal],
            'demos': [demo],
            'touches': [touch]
        }
        
        timeline = build_timeline(events)
        assert len(timeline) == 3
        
        # Check chronological order
        assert timeline[0].t == 1.0
        assert timeline[0].type == "DEMO"
        assert timeline[1].t == 2.0
        assert timeline[1].type == "GOAL"
        assert timeline[2].t == 3.0
        assert timeline[2].type == "TOUCH"
    
    def test_timeline_event_data_preserved(self):
        """Timeline events preserve original event data."""
        goal = GoalEvent(t=1.0, scorer="p1", team="BLUE", shot_speed_kph=120.0)
        events = {'goals': [goal]}
        
        timeline = build_timeline(events)
        assert len(timeline) == 1
        
        event = timeline[0]
        assert event.type == "GOAL"
        assert event.player_id == "p1"
        assert event.team == "BLUE"
        assert event.data["shot_speed_kph"] == 120.0
    
    def test_same_timestamp_stable_sort(self):
        """Events with same timestamp sorted by type for stability."""
        events = {
            'touches': [TouchEvent(t=1.0, player_id="p1", location=Vec3(0.0, 0.0, 0.0))],
            'demos': [DemoEvent(t=1.0, victim="p2", attacker="p1")],
            'goals': [GoalEvent(t=1.0, scorer="p1", team="BLUE")]
        }
        
        timeline = build_timeline(events)
        assert len(timeline) == 3
        
        # Should be sorted alphabetically by type: DEMO, GOAL, TOUCH
        assert timeline[0].type == "DEMO"
        assert timeline[1].type == "GOAL"
        assert timeline[2].type == "TOUCH"
