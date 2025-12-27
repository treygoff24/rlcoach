"""Tests for possession and passing analysis."""

from rlcoach.analysis.passing import analyze_passing
from rlcoach.events import TouchEvent
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame


def make_frame(t: float, ball_pos: Vec3, ball_vel: Vec3, players: list[PlayerFrame]) -> Frame:
    return Frame(
        timestamp=t,
        ball=BallFrame(position=ball_pos, velocity=ball_vel, angular_velocity=Vec3(0.0, 0.0, 0.0)),
        players=players,
    )


def make_player(pid: str, team: int, pos: Vec3 = Vec3(0.0, 0.0, 17.0)) -> PlayerFrame:
    return PlayerFrame(
        player_id=pid,
        team=team,
        position=pos,
        velocity=Vec3(0.0, 0.0, 0.0),
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=33,
        is_supersonic=False,
        is_on_ground=True,
        is_demolished=False,
    )


class TestPassingAnalysis:
    def test_empty_returns_zeros_for_player(self):
        result = analyze_passing([], {}, player_id="p1")
        assert result == {
            "passes_completed": 0,
            "passes_attempted": 0,
            "passes_received": 0,
            "turnovers": 0,
            "give_and_go_count": 0,
            "possession_time_s": 0.0,
        }

    def test_team_pass_give_and_go_and_turnover(self):
        # Players: BLUE team pA, pB; ORANGE team pC
        pA0 = make_player("A", 0)
        pB0 = make_player("B", 0)
        pC1 = make_player("C", 1)

        # Frames across 0..3.0s, ball generally moving toward +Y (BLUE attacks +Y)
        frames = [
            make_frame(0.0, Vec3(0.0, -1200.0, 93.0), Vec3(0.0, 500.0, 0.0), [pA0, pB0, pC1]),
            make_frame(0.5, Vec3(0.0, -900.0, 93.0), Vec3(0.0, 500.0, 0.0), [pA0, pB0, pC1]),
            make_frame(1.0, Vec3(0.0, -600.0, 93.0), Vec3(0.0, 500.0, 0.0), [pA0, pB0, pC1]),
            make_frame(1.5, Vec3(0.0, -300.0, 93.0), Vec3(0.0, 500.0, 0.0), [pA0, pB0, pC1]),
            make_frame(2.4, Vec3(0.0, -100.0, 93.0), Vec3(0.0, 500.0, 0.0), [pA0, pB0, pC1]),
            make_frame(3.0, Vec3(0.0, 200.0, 93.0), Vec3(0.0, 500.0, 0.0), [pA0, pB0, pC1]),
        ]

        # Touch sequence (times must align with frames timestamps window):
        # A (BLUE) -> B (BLUE) within 0.9s and +Y delta: completed pass
        # Then B (BLUE) -> A (BLUE) within 1.3s and +Y delta: completed, give-and-go
        # Then C (ORANGE) touch: turnover against BLUE
        touches = [
            TouchEvent(t=0.0, player_id="A", location=Vec3(0.0, -1000.0, 17.0)),
            TouchEvent(t=0.9, player_id="B", location=Vec3(0.0, -500.0, 17.0)),
            TouchEvent(t=2.2, player_id="A", location=Vec3(0.0, -200.0, 17.0)),
            TouchEvent(t=3.0, player_id="C", location=Vec3(0.0, 500.0, 17.0)),
        ]
        events = {"touches": touches}

        # Team-level analysis for BLUE
        result_blue = analyze_passing(frames, events, team="BLUE")

        assert result_blue["passes_attempted"] == 2  # A->B and B->A attempts
        assert result_blue["passes_completed"] == 2
        assert result_blue["passes_received"] == 2
        assert result_blue["give_and_go_count"] == 1
        assert result_blue["turnovers"] == 1  # C touch after BLUE possession

        # Possession: BLUE should have near full 0..3.0s (ball not toward own half fast)
        # Exact depends on frame spacing; require >= (last timestamp) - small epsilon
        assert result_blue["possession_time_s"] >= 2.9

        # Player-level spot checks
        result_A = analyze_passing(frames, events, player_id="A")
        result_B = analyze_passing(frames, events, player_id="B")
        # A initiated one pass and received one
        assert result_A["passes_attempted"] == 1
        assert result_A["passes_completed"] == 1
        assert result_A["passes_received"] == 1
        # B initiated one pass and received one; both part of give-and-go
        assert result_B["passes_attempted"] == 1
        assert result_B["passes_completed"] == 1
        assert result_B["passes_received"] == 1

    def test_diagonal_forward_progress_is_counted(self):
        pA0 = make_player("A", 0, Vec3(-200.0, -800.0, 17.0))
        pB0 = make_player("B", 0, Vec3(200.0, -720.0, 17.0))

        frames = [
            make_frame(0.0, Vec3(0.0, -820.0, 93.0), Vec3(0.0, 0.0, 0.0), [pA0, pB0]),
            make_frame(0.5, Vec3(0.0, -700.0, 93.0), Vec3(0.0, 0.0, 0.0), [pA0, pB0]),
        ]

        touches = [
            TouchEvent(t=0.0, player_id="A", location=Vec3(-200.0, -820.0, 17.0)),
            TouchEvent(t=0.4, player_id="B", location=Vec3(120.0, -700.0, 17.0)),
        ]

        result_blue = analyze_passing(frames, {"touches": touches}, team="BLUE")
        assert result_blue["passes_completed"] == 1
        assert result_blue["passes_attempted"] == 1
