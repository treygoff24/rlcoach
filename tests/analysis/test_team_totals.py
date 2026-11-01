"""Team totals add players up in a fixed order.

Float addition depends on order, so looping over a set of player IDs gives a team
of three or more slightly different totals from one run to the next.
"""

from unittest.mock import Mock

from rlcoach.analysis import _aggregate_team_mechanics, boost, movement, positioning
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame

# Six IDs, because a set of six strings rarely iterates in sorted order
PLAYER_IDS = [f"player_{index}" for index in range(6)]


def _team_frames() -> list[Frame]:
    zero = Vec3(0.0, 0.0, 0.0)
    return [
        Frame(
            timestamp=0.0,
            ball=BallFrame(position=zero, velocity=zero, angular_velocity=zero),
            players=[
                PlayerFrame(
                    player_id=player_id,
                    team=0,
                    position=zero,
                    velocity=zero,
                    rotation=zero,
                    boost_amount=33,
                )
                for player_id in PLAYER_IDS
            ],
        )
    ]


def test_team_movement_adds_players_in_sorted_order(monkeypatch):
    seen = []

    def analyze_player(frames, player_id):
        seen.append(player_id)
        return movement._empty_movement()

    monkeypatch.setattr(movement, "_analyze_player_movement", analyze_player)

    movement._analyze_team_movement(_team_frames(), "BLUE")

    assert seen == sorted(PLAYER_IDS)


def test_team_positioning_adds_players_in_sorted_order(monkeypatch):
    seen = []

    def analyze_player(frames, player_id):
        seen.append(player_id)
        return positioning._empty_positioning(team_size=1)

    monkeypatch.setattr(positioning, "_analyze_player_positioning", analyze_player)

    positioning._analyze_team_positioning(_team_frames(), "BLUE")

    assert seen == sorted(PLAYER_IDS)


def test_team_boost_adds_players_in_sorted_order(monkeypatch):
    seen = []

    def analyze_player(frames, frame_timestamps, pickups, player_id, match_duration):
        seen.append(player_id)
        return boost._empty_boost()

    monkeypatch.setattr(boost, "_analyze_player_boost", analyze_player)

    boost._analyze_team_boost(_team_frames(), [0.0], [], "BLUE", 60.0)

    assert seen == sorted(PLAYER_IDS)


def test_team_mechanics_adds_players_in_sorted_order():
    per_player = Mock()
    per_player.get.return_value = {}

    _aggregate_team_mechanics(_team_frames(), "BLUE", {"per_player": per_player})

    seen = [call.args[0] for call in per_player.get.call_args_list]
    assert seen == sorted(PLAYER_IDS)
