from rlcoach.field_constants import Vec3
from rlcoach.parser.types import Quaternion, Rotation

from . import (
    create_component_event,
    create_simple_replay_frames,
    create_test_frame,
    create_test_player,
    with_flip_at,
)


def test_create_test_player_accepts_parser_signals() -> None:
    player = create_test_player(
        "player1",
        0,
        velocity=Vec3(2301.0, 0.0, 0.0),
        angular_velocity=Vec3(1.0, 2.0, 3.0),
        rotation=Vec3(0.1, 0.2, 0.3),
        quaternion=Quaternion(0.0, 0.0, 0.0, 1.0),
        throttle=0.5,
        steer=-0.25,
        handbrake=True,
        throttle_raw=192,
        steer_raw=96,
        boost_active=True,
        boost_active_raw=3,
        boost_amount_raw=200,
        boost_grant_count=4,
        is_jumping=True,
        is_dodging=False,
        is_double_jumping=True,
        jump_active_raw=1,
        dodge_active_raw=2,
        double_jump_active_raw=5,
        sleeping=True,
    )

    assert player.angular_velocity == Vec3(1.0, 2.0, 3.0)
    assert isinstance(player.rotation, Rotation)
    assert player.rotation.quaternion == Quaternion(0.0, 0.0, 0.0, 1.0)
    assert player.throttle == 0.5
    assert player.steer == -0.25
    assert player.handbrake is True
    assert player.throttle_raw == 192
    assert player.steer_raw == 96
    assert player.boost_active is True
    assert player.boost_active_raw == 3
    assert player.boost_amount_raw == 200
    assert player.boost_grant_count == 4
    assert player.is_supersonic is True
    assert player.is_jumping is True
    assert player.is_dodging is False
    assert player.is_double_jumping is True
    assert player.jump_active_raw == 1
    assert player.dodge_active_raw == 2
    assert player.double_jump_active_raw == 5
    assert player.sleeping is True


def test_create_test_frame_accepts_component_events() -> None:
    event = create_component_event(
        timestamp=1.25,
        kind="air_activate_count",
        component="air_activate",
        player_id="player1",
        raw_value=2,
    )
    frame = create_test_frame(
        1.25,
        [create_test_player("player1", 0)],
        component_events=[event],
    )

    assert frame.component_events == [event]


def test_with_flip_at_adds_dodge_torque_to_nearest_frame() -> None:
    frames = create_simple_replay_frames(
        duration_seconds=1.0,
        frame_rate=2.0,
        players=[("player1", 0)],
    )

    updated = with_flip_at(frames, 0.4, "player1", Vec3(0.0, 1.0, 0.0))

    assert frames[1].component_events == []
    assert updated[1].component_events[0].kind == "dodge_torque"
    assert updated[1].component_events[0].component == "dodge"
    assert updated[1].component_events[0].player_id == "player1"
    assert updated[1].component_events[0].vector == Vec3(0.0, 1.0, 0.0)
