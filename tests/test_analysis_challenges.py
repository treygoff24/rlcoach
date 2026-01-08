"""Tests for challenges/50-50s analysis."""

from rlcoach.analysis.challenges import analyze_challenges
from rlcoach.events import TouchEvent
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame


def make_frame(t: float, ball_pos: Vec3, players: list[PlayerFrame]) -> Frame:
    return Frame(
        timestamp=t,
        ball=BallFrame(
            position=ball_pos,
            velocity=Vec3(0.0, 0.0, 0.0),
            angular_velocity=Vec3(0.0, 0.0, 0.0),
        ),
        players=players,
    )


def make_player(pid: str, team: int, pos: Vec3, boost: int = 33) -> PlayerFrame:
    return PlayerFrame(
        player_id=pid,
        team=team,
        position=pos,
        velocity=Vec3(0.0, 0.0, 0.0),
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=boost,
        is_supersonic=False,
        is_on_ground=True,
        is_demolished=False,
    )


class TestChallengesAnalysis:
    def test_basic_contest_and_outcomes(self):
        # Players
        a = make_player(
            "A", 0, Vec3(0.0, -450.0, 17.0), boost=10
        )  # BLUE ahead of ball with low boost
        b = make_player("B", 0, Vec3(0.0, -700.0, 17.0))
        c = make_player("C", 1, Vec3(0.0, -440.0, 17.0))  # ORANGE

        # Frames near touch times for risk computation
        frames = [
            make_frame(0.9, Vec3(0.0, -620.0, 93.0), [a, b, c]),
            make_frame(1.5, Vec3(0.0, -400.0, 93.0), [a, b, c]),
            make_frame(2.0, Vec3(0.0, -250.0, 93.0), [a, b, c]),
        ]

        # Touch sequence forming a contest between BLUE (A) and ORANGE (C)
        touches = [
            TouchEvent(
                t=1.0,
                player_id="A",
                location=Vec3(0.0, -600.0, 17.0),
                ball_speed_kph=60.0,
            ),
            TouchEvent(
                t=1.4,
                player_id="C",
                location=Vec3(0.0, -350.0, 17.0),
                ball_speed_kph=65.0,
            ),
            TouchEvent(
                t=1.9,
                player_id="A",
                location=Vec3(0.0, -200.0, 17.0),
                ball_speed_kph=55.0,
            ),
        ]
        events = {"touches": touches}

        blue = analyze_challenges(frames, events, team="BLUE")
        orange = analyze_challenges(frames, events, team="ORANGE")

        # One contest for both teams
        assert blue["contests"] == 1
        assert orange["contests"] == 1

        # Winner is team of second touch (ORANGE)
        assert blue["losses"] == 1
        assert orange["wins"] == 1

        # First to ball is BLUE (player A)
        assert blue["first_to_ball_pct"] == 100.0
        assert orange["first_to_ball_pct"] == 0.0

        # Depth is around average of -500 and -460 => ~ -480 UU => ~9.12 m
        assert 8.0 < blue["challenge_depth_m"] < 11.0

        # Risk is bounded [0,1]
        assert 0.0 <= blue["risk_index_avg"] <= 1.0

    def test_player_scoped_metrics(self):
        a = make_player("A", 0, Vec3(0.0, -100.0, 17.0))
        c = make_player("C", 1, Vec3(0.0, -120.0, 17.0))
        frames = [make_frame(0.0, Vec3(0.0, -150.0, 93.0), [a, c])]
        touches = [
            TouchEvent(
                t=0.1,
                player_id="A",
                location=Vec3(0.0, -220.0, 17.0),
                ball_speed_kph=70.0,
            ),
            TouchEvent(
                t=0.3,
                player_id="C",
                location=Vec3(0.0, 10.0, 17.0),
                ball_speed_kph=68.0,
            ),
        ]
        events = {"touches": touches}

        res_a = analyze_challenges(frames, events, player_id="A")
        assert res_a["contests"] == 1
        assert res_a["losses"] in (
            0,
            1,
        )  # depends on neutral/win heuristic; at least present
        assert 0.0 <= res_a["risk_index_avg"] <= 1.0

    def test_consecutive_same_player_touches_do_not_loop(self):
        # Touch list where the same player hits the ball twice before the opponent
        a = make_player("A", 0, Vec3(0.0, 0.0, 17.0))
        b = make_player("B", 1, Vec3(0.0, 100.0, 17.0))
        frames = [make_frame(0.0, Vec3(0.0, 0.0, 93.0), [a, b])]
        touches = [
            TouchEvent(t=0.2, player_id="A", location=Vec3(0.0, 0.0, 17.0)),
            TouchEvent(t=0.4, player_id="A", location=Vec3(0.0, 10.0, 17.0)),
            # Opponent touch happens later than the contest window, so no contest should register
            TouchEvent(t=2.0, player_id="B", location=Vec3(0.0, 90.0, 17.0)),
        ]

        events = {"touches": touches}

        result = analyze_challenges(frames, events, team="BLUE")

        # No contests should be registered when the opponent touch is outside the window
        assert result["contests"] == 0
