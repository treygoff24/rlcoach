"""Tests for the normalization layer."""

import pytest
from unittest.mock import Mock

from rlcoach.normalize import (
    measure_frame_rate,
    to_field_coords,
    normalize_players,
    build_timeline,
    GOAL_POST_BUFFER_S,
)
from rlcoach.field_constants import Vec3, FIELD
from rlcoach.parser.types import Header, PlayerInfo, NetworkFrames, Frame, GoalHeader


class TestFrameRateMeasurement:
    """Test frame rate calculation from timestamps."""
    
    def test_empty_frames_returns_default(self):
        """Empty frame list returns default 30 FPS."""
        assert measure_frame_rate([]) == 30.0
    
    def test_single_frame_returns_default(self):
        """Single frame returns default 30 FPS."""
        frame = Mock()
        frame.timestamp = 1.0
        assert measure_frame_rate([frame]) == 30.0
    
    def test_consistent_30fps(self):
        """Consistent 30 FPS timestamps."""
        frames = []
        for i in range(10):
            frame = Mock()
            frame.timestamp = i / 30.0  # 30 FPS
            frames.append(frame)
        
        fps = measure_frame_rate(frames)
        assert 29.5 <= fps <= 30.5  # Allow small tolerance
    
    def test_consistent_60fps(self):
        """Consistent 60 FPS timestamps."""
        frames = []
        for i in range(10):
            frame = Mock()
            frame.timestamp = i / 60.0  # 60 FPS
            frames.append(frame)
        
        fps = measure_frame_rate(frames)
        assert 59.0 <= fps <= 61.0
    
    def test_variable_sampling_uses_median(self):
        """Variable frame timing uses median delta."""
        frames = [
            Mock(timestamp=0.0),
            Mock(timestamp=1/30),    # Normal frame
            Mock(timestamp=2/30),    # Normal frame  
            Mock(timestamp=5/30),    # Dropped frames (large gap)
            Mock(timestamp=6/30),    # Back to normal
            Mock(timestamp=7/30),    # Normal frame
        ]
        
        fps = measure_frame_rate(frames)
        assert 29.0 <= fps <= 31.0  # Should use median ~30 FPS
    
    def test_dict_format_timestamps(self):
        """Handle dict format with timestamp key."""
        frames = [
            {'timestamp': 0.0},
            {'timestamp': 1/30},
            {'timestamp': 2/30},
        ]
        
        fps = measure_frame_rate(frames)
        assert 29.0 <= fps <= 31.0
    
    def test_time_key_format(self):
        """Handle frames with 'time' key instead of 'timestamp'."""
        frames = [
            Mock(time=0.0),
            Mock(time=1/30),
            Mock(time=2/30),
        ]
        
        fps = measure_frame_rate(frames)
        assert 29.0 <= fps <= 31.0
    
    def test_fps_clamping(self):
        """FPS is clamped to reasonable range."""
        # Test very low FPS
        frames = [Mock(timestamp=0.0), Mock(timestamp=10.0)]
        fps = measure_frame_rate(frames)
        assert fps >= 1.0
        
        # Test very high FPS
        frames = [Mock(timestamp=0.0), Mock(timestamp=0.001)]
        fps = measure_frame_rate(frames)
        assert fps <= 240.0


class TestCoordinateTransformation:
    """Test coordinate system transformation."""
    
    def test_vec3_passthrough(self):
        """Vec3 objects passed through unchanged."""
        vec = Vec3(100.0, 200.0, 300.0)
        result = to_field_coords(vec)
        assert result == vec
    
    def test_object_with_xyz_attrs(self):
        """Objects with x,y,z attributes."""
        obj = Mock(x=100.0, y=200.0, z=300.0)
        result = to_field_coords(obj)
        assert result == Vec3(100.0, 200.0, 300.0)
    
    def test_tuple_list_conversion(self):
        """Tuples and lists converted to Vec3."""
        assert to_field_coords((100, 200, 300)) == Vec3(100.0, 200.0, 300.0)
        assert to_field_coords([100, 200, 300]) == Vec3(100.0, 200.0, 300.0)
    
    def test_dict_conversion(self):
        """Dict format converted to Vec3."""
        coord_dict = {'x': 100, 'y': 200, 'z': 300}
        result = to_field_coords(coord_dict)
        assert result == Vec3(100.0, 200.0, 300.0)
    
    def test_missing_dict_keys_default_zero(self):
        """Missing dict keys default to 0."""
        coord_dict = {'x': 100}  # Missing y, z
        result = to_field_coords(coord_dict)
        assert result == Vec3(100.0, 0.0, 0.0)
    
    def test_field_boundary_clamping(self):
        """Coordinates clamped to field boundaries with tolerance."""
        # Test X boundary
        over_x = to_field_coords((10000, 0, 0))
        assert over_x.x <= FIELD.SIDE_WALL_X * 1.1
        
        under_x = to_field_coords((-10000, 0, 0))
        assert under_x.x >= -FIELD.SIDE_WALL_X * 1.1
        
        # Test Y boundary  
        over_y = to_field_coords((0, 10000, 0))
        assert over_y.y <= FIELD.BACK_WALL_Y * 1.1
        
        # Test Z boundary
        over_z = to_field_coords((0, 0, 10000))
        assert over_z.z <= FIELD.CEILING_Z * 2.0
        
        under_z = to_field_coords((0, 0, -1000))
        assert under_z.z >= -100.0
    
    def test_invalid_input_returns_origin(self):
        """Invalid input returns origin."""
        assert to_field_coords("invalid") == Vec3(0.0, 0.0, 0.0)
        assert to_field_coords(None) == Vec3(0.0, 0.0, 0.0)
        assert to_field_coords(123) == Vec3(0.0, 0.0, 0.0)
    
    def test_non_numeric_values_return_origin(self):
        """Non-numeric coordinate values return origin."""
        bad_dict = {'x': 'not_a_number', 'y': 200, 'z': 300}
        result = to_field_coords(bad_dict)
        assert result == Vec3(0.0, 0.0, 0.0)


class TestPlayerNormalization:
    """Test player identity mapping."""
    
    def test_header_only_players(self):
        """Player mapping from header only."""
        header = Header(
            players=[
                PlayerInfo(name="Player1", platform_id="steam_123", team=0, score=100),
                PlayerInfo(name="Player2", platform_id="epic_456", team=1, score=200),
            ]
        )
        
        result = normalize_players(header, [])
        
        assert "steam_123" in result
        assert result["steam_123"]["name"] == "Player1"
        assert result["steam_123"]["team"] == 0
        assert result["steam_123"]["score"] == 100
        
        assert "epic_456" in result
        assert result["epic_456"]["name"] == "Player2"
        assert result["epic_456"]["team"] == 1
    
    def test_players_without_platform_id(self):
        """Players without platform_id get positional IDs."""
        header = Header(
            players=[
                PlayerInfo(name="Player1", team=0),
                PlayerInfo(name="Player2", team=1),
            ]
        )
        
        result = normalize_players(header, [])
        
        assert "player_0" in result
        assert result["player_0"]["name"] == "Player1"
        assert "player_1" in result
        assert result["player_1"]["name"] == "Player2"
    
    def test_empty_header_players(self):
        """Empty player list handled gracefully."""
        header = Header(players=[])
        result = normalize_players(header, [])
        assert result == {}
    
    def test_frame_player_augmentation(self):
        """Frame data augments header information."""
        header = Header(
            players=[
                PlayerInfo(name="Player1", team=0),
                PlayerInfo(name="Player2", team=1),
            ]
        )
        
        # Mock frame with different player IDs
        frame = Mock()
        frame.players = [
            Mock(player_id="frame_player_0"),
            Mock(player_id="frame_player_1"),
        ]
        
        result = normalize_players(header, [frame])
        
        # Should have both header and frame mappings
        assert "player_0" in result
        assert "frame_player_0" in result
        assert result["frame_player_0"]["alias_for"] == "player_0"


class TestTimelineBuilding:
    """Test normalized timeline construction."""
    
    def test_header_only_timeline(self):
        """Header-only creates minimal timeline."""
        header = Header(
            team_size=2,
            match_length=300.0,
            players=[
                PlayerInfo(name="Player1", team=0),
                PlayerInfo(name="Player2", team=1),
            ]
        )
        
        timeline = build_timeline(header, [])
        
        assert len(timeline) == 1
        frame = timeline[0]
        assert frame.timestamp == 0.0
        assert frame.ball.position.z == 93.15  # Ball spawn height
        assert len(frame.players) == 0  # No frame data
    
    def test_single_frame_timeline(self):
        """Single frame creates valid timeline."""
        header = Header(
            players=[PlayerInfo(name="Player1", team=0)]
        )
        
        # Mock frame data
        frame_data = Mock()
        frame_data.timestamp = 1.5
        frame_data.ball = Mock()
        frame_data.ball.position = Mock(x=100, y=200, z=300)
        frame_data.ball.velocity = Mock(x=10, y=20, z=30)
        frame_data.ball.angular_velocity = Mock(x=1, y=2, z=3)
        frame_data.players = []
        
        timeline = build_timeline(header, [frame_data])

        assert len(timeline) == 1
        frame = timeline[0]
        assert frame.timestamp == 0.0
        assert frame.ball.position == Vec3(100.0, 200.0, 300.0)
        assert frame.ball.velocity == Vec3(10.0, 20.0, 30.0)
    
    def test_multiple_frames_sorted_by_timestamp(self):
        """Multiple frames sorted chronologically."""
        header = Header()
        
        # Create frames out of order
        frame1 = Mock(timestamp=2.0, ball=Mock(), players=[])
        frame1.ball.position = Mock(x=0, y=0, z=93.15)
        frame1.ball.velocity = Mock(x=0, y=0, z=0)
        frame1.ball.angular_velocity = Mock(x=0, y=0, z=0)
        
        frame2 = Mock(timestamp=1.0, ball=Mock(), players=[])
        frame2.ball.position = Mock(x=0, y=0, z=93.15)
        frame2.ball.velocity = Mock(x=0, y=0, z=0)
        frame2.ball.angular_velocity = Mock(x=0, y=0, z=0)
        
        timeline = build_timeline(header, [frame1, frame2])

        assert len(timeline) == 2
        assert timeline[0].timestamp == 0.0  # Earlier frame becomes t=0
        assert timeline[1].timestamp == 1.0
    
    def test_player_frame_extraction(self):
        """Player data extracted correctly from frames."""
        header = Header(
            players=[PlayerInfo(name="TestPlayer", platform_id="test_123", team=0)]
        )
        
        # Mock frame with player data
        frame_data = Mock()
        frame_data.timestamp = 1.0
        frame_data.ball = Mock()
        frame_data.ball.position = Mock(x=0, y=0, z=93.15)
        frame_data.ball.velocity = Mock(x=0, y=0, z=0)
        frame_data.ball.angular_velocity = Mock(x=0, y=0, z=0)
        
        player_data = Mock()
        player_data.player_id = "test_123"
        player_data.team = 0
        player_data.position = Mock(x=1000, y=2000, z=17)
        player_data.velocity = Mock(x=500, y=0, z=0)
        player_data.rotation = Mock(x=0, y=1.57, z=0)
        player_data.boost_amount = 75
        player_data.is_supersonic = True
        player_data.is_on_ground = True
        player_data.is_demolished = False
        
        frame_data.players = [player_data]
        
        timeline = build_timeline(header, [frame_data])
        
        assert len(timeline) == 1
        frame = timeline[0]
        assert len(frame.players) == 1
        
        player_frame = frame.players[0]
        assert player_frame.player_id == "test_123"
        assert player_frame.team == 0
        assert player_frame.position == Vec3(1000.0, 2000.0, 17.0)
        assert player_frame.velocity == Vec3(500.0, 0.0, 0.0)
        assert player_frame.boost_amount == 75
        assert player_frame.is_supersonic is True
    
    def test_malformed_frame_skipped(self):
        """Malformed frames are skipped gracefully."""
        header = Header()
        
        # Mix of good and bad frames
        good_frame = Mock()
        good_frame.timestamp = 1.0
        good_frame.ball = Mock(position=Mock(x=0, y=0, z=93.15), velocity=Mock(x=0, y=0, z=0))
        good_frame.ball.angular_velocity = Mock(x=0, y=0, z=0)
        good_frame.players = []
        
        bad_frame = Mock()
        bad_frame.timestamp = "not_a_number"  # Invalid timestamp
        
        timeline = build_timeline(header, [good_frame, bad_frame])

        assert len(timeline) == 1  # Only good frame
        assert timeline[0].timestamp == 0.0

    def test_post_game_frames_trimmed_by_header_length(self):
        """Frames beyond header match length are pruned after alignment."""
        header = Header(match_length=1.0)

        def make_frame(ts: float):
            ball = Mock()
            ball.position = Mock(x=0, y=0, z=93.15)
            ball.velocity = Mock(x=0, y=0, z=0)
            ball.angular_velocity = Mock(x=0, y=0, z=0)
            frame = Mock()
            frame.timestamp = ts
            frame.ball = ball
            frame.players = []
            return frame

        frames = [
            make_frame(5.0),
            make_frame(5.5),
            make_frame(7.0),  # Beyond match length window
        ]

        timeline = build_timeline(header, frames)

        assert len(timeline) == 2
        assert timeline[0].timestamp == 0.0
        assert timeline[1].timestamp == 0.5

    def test_goal_buffer_extends_beyond_header_duration(self):
        """Goal metadata keeps frames when header duration is too short."""
        header = Header(match_length=0.5, goals=[GoalHeader(frame=90, player_name="Player", player_team=0)])

        def make_frame(ts: float):
            ball = Mock()
            ball.position = Mock(x=0, y=0, z=93.15)
            ball.velocity = Mock(x=0, y=0, z=0)
            ball.angular_velocity = Mock(x=0, y=0, z=0)
            frame = Mock()
            frame.timestamp = ts
            frame.ball = ball
            frame.players = []
            return frame

        start = 10.0
        frames = [make_frame(start + i / 30.0) for i in range(120)]

        timeline = build_timeline(header, frames)

        # Without goal metadata we'd clamp near 0.5 seconds; ensure we kept longer span
        assert timeline[-1].timestamp > GOAL_POST_BUFFER_S / 2
        assert len(timeline) == len(frames)

    def test_dict_format_frames(self):
        """Dict format frames handled correctly."""
        header = Header()
        
        frame_dict = {
            'timestamp': 1.5,
            'ball': {
                'position': {'x': 100, 'y': 200, 'z': 300},
                'velocity': {'x': 10, 'y': 20, 'z': 30},
                'angular_velocity': {'x': 1, 'y': 2, 'z': 3}
            },
            'players': []
        }
        
        timeline = build_timeline(header, [frame_dict])
        
        assert len(timeline) == 1
        frame = timeline[0]
        assert frame.timestamp == 0.0
        assert frame.ball.position == Vec3(100.0, 200.0, 300.0)
        assert frame.ball.velocity == Vec3(10.0, 20.0, 30.0)


class TestIntegration:
    """Integration tests combining multiple normalization functions."""
    
    def test_full_normalization_pipeline(self):
        """Full pipeline from raw data to normalized timeline."""
        # Create realistic header
        header = Header(
            playlist_id="STANDARD",
            map_name="DFH Stadium",
            team_size=3,
            team0_score=2,
            team1_score=1,
            match_length=300.0,
            players=[
                PlayerInfo(name="Player1", platform_id="steam_123", team=0, score=250),
                PlayerInfo(name="Player2", platform_id="epic_456", team=1, score=100),
            ]
        )
        
        # Create frame sequence
        frames = []
        for i in range(5):
            timestamp = i / 30.0  # 30 FPS
            
            frame = Mock()
            frame.timestamp = timestamp
            
            # Ball data
            frame.ball = Mock()
            frame.ball.position = Mock(x=i*100, y=i*50, z=93.15 + i*10)
            frame.ball.velocity = Mock(x=100, y=50, z=10)
            frame.ball.angular_velocity = Mock(x=0.1, y=0.2, z=0.3)
            
            # Player data
            player1 = Mock()
            player1.player_id = "steam_123"
            player1.team = 0
            player1.position = Mock(x=-1000 + i*100, y=-2000 + i*200, z=17)
            player1.velocity = Mock(x=800, y=0, z=0)
            player1.rotation = Mock(x=0, y=0, z=0)
            player1.boost_amount = 100 - i*10
            
            player2 = Mock()
            player2.player_id = "epic_456"  
            player2.team = 1
            player2.position = Mock(x=1000 - i*100, y=2000 - i*200, z=17)
            player2.velocity = Mock(x=-600, y=100, z=0)
            player2.rotation = Mock(x=0, y=3.14, z=0)
            player2.boost_amount = 50 + i*5
            
            frame.players = [player1, player2]
            frames.append(frame)
        
        # Test full pipeline
        fps = measure_frame_rate(frames)
        assert 29.0 <= fps <= 31.0
        
        players_index = normalize_players(header, frames)
        assert "steam_123" in players_index
        assert "epic_456" in players_index
        
        timeline = build_timeline(header, frames)
        assert len(timeline) == 5
        
        # Verify first frame
        first_frame = timeline[0]
        assert first_frame.timestamp == 0.0
        assert len(first_frame.players) == 2
        
        # Verify progression
        last_frame = timeline[-1]
        assert last_frame.timestamp == 4/30.0
        assert last_frame.ball.position.x == 400.0  # 4*100
        
        # Verify player data
        player1_frame = last_frame.get_player_by_id("steam_123")
        assert player1_frame is not None
        assert player1_frame.team == 0
        assert player1_frame.boost_amount == 60  # 100 - 4*10
        
        # Test team filtering
        team0_players = last_frame.get_players_by_team(0)
        team1_players = last_frame.get_players_by_team(1)
        assert len(team0_players) == 1
        assert len(team1_players) == 1
        assert team0_players[0].player_id == "steam_123"
        assert team1_players[0].player_id == "epic_456"
