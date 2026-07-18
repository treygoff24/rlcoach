from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from rlcoach import input_timeline
from rlcoach.input_timeline import (
    ChannelValue,
    InputSample,
    SolvedEvent,
    build_solver_payload,
    mirror_solve_output,
    solve_input_timelines,
)
from rlcoach.parser.types import (
    Frame,
    Header,
    ParserDemoEvent,
    ParserKickoffMarker,
    ParserTouchEvent,
    Quaternion,
    Rotation,
)

_BUILDERS_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "builders.py"
_BUILDERS_SPEC = importlib.util.spec_from_file_location(
    "input_timeline_builders", _BUILDERS_PATH
)
assert _BUILDERS_SPEC is not None
_builders = importlib.util.module_from_spec(_BUILDERS_SPEC)
assert _BUILDERS_SPEC.loader is not None
_BUILDERS_SPEC.loader.exec_module(_builders)

create_component_event = _builders.create_component_event
create_test_ball = _builders.create_test_ball
create_test_frame = _builders.create_test_frame
create_test_player = _builders.create_test_player


def _frames() -> list[Frame]:
    frames = []
    for idx in range(3):
        frames.append(
            create_test_frame(
                timestamp=idx / 30.0,
                players=[
                    create_test_player(
                        "player_0",
                        0,
                        quaternion=Quaternion(0.0, 0.0, 0.0, 1.0),
                        rotation=Rotation(0.0, 0.0, 0.0),
                        throttle_raw=128 + idx,
                        steer_raw=127,
                        boost_active=idx == 2,
                        boost_amount_raw=80,
                        jump_active_raw=idx % 2,
                        dodge_active_raw=0,
                        double_jump_active_raw=0,
                        is_on_ground=idx == 0,
                    )
                ],
                ball=create_test_ball(),
            )
        )

    frames[1] = Frame(
        timestamp=frames[1].timestamp,
        ball=frames[1].ball,
        players=frames[1].players,
        component_events=[
            create_component_event(
                timestamp=frames[1].timestamp,
                kind="dodge_torque",
                component="dodge",
                player_id="player_0",
            )
        ],
        parser_touch_events=[
            ParserTouchEvent(
                timestamp=frames[1].timestamp,
                player_id="player_0",
                team=0,
                frame_index=1,
            )
        ],
        parser_demo_events=[
            ParserDemoEvent(
                timestamp=frames[1].timestamp,
                victim_id="player_0",
                attacker_id=None,
                frame_index=1,
            )
        ],
        parser_kickoff_markers=[
            ParserKickoffMarker(
                timestamp=frames[1].timestamp,
                phase="INITIAL",
                frame_index=1,
            )
        ],
        delta=1 / 30.0,
    )
    return frames


def test_build_solver_payload_uses_flat_columnar_arrays() -> None:
    payload = build_solver_payload(
        _frames(), Header(engine_build="250909.54128.495700")
    )

    assert payload["build_bucket"] == "250909.54128.495700"
    assert payload["deltas"] == [0.0, 1 / 30.0, 1 / 30.0]
    assert len(payload["ball"]["pos"]) == 9

    player = payload["players"][0]
    assert player["player_id"] == "player_0"
    assert player["frames"]["pos"] == [0.0, 0.0, 17.0] * 3
    assert len(player["frames"]["quat_xyzw"]) == 12
    assert player["replicated"]["throttle_raw"] == [128, 129, 130]
    assert player["replicated"]["boost_active_raw"] == [False, False, True]
    assert player["component"]["jump_raw"] == [0, 1, 0]
    assert player["component"]["events"][0]["component"] == "DodgeTorque"
    assert payload["touch_events"][0]["player_id"] == "player_0"
    assert payload["demo_events"][0]["victim_id"] == "player_0"
    assert payload["kickoff_markers"][0]["phase"] == "INITIAL"


def test_solver_degrades_to_none_without_wheel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RLCOACH_INPUT_SOLVER", raising=False)
    monkeypatch.setattr(input_timeline.importlib, "import_module", _raise_import)

    assert solve_input_timelines(_frames(), Header()) is None


def test_solver_import_propagates_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        input_timeline.importlib,
        "import_module",
        lambda _: (_ for _ in ()).throw(RuntimeError("broken wheel")),
    )

    with pytest.raises(RuntimeError, match="broken wheel"):
        solve_input_timelines(_frames(), Header())


def test_solver_off_switch_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RLCOACH_INPUT_SOLVER", "off")
    monkeypatch.setattr(
        input_timeline, "_load_solver", lambda: SimpleNamespace(solve_timeline=None)
    )

    assert solve_input_timelines(_frames(), Header()) is None


def test_dict_output_mirrors_to_frozen_dataclasses() -> None:
    raw = {
        "timelines": [
            {
                "player_id": "player_0",
                "samples": [
                    {
                        "frame_index": 7,
                        "tick_range": [28, 32],
                        "time_range": [1.0, 1.0333],
                        "throttle": _channel(1.0),
                        "steer": _channel(0.0),
                        "pitch": _channel(0.0),
                        "yaw": _channel(0.0),
                        "roll": _channel(0.0),
                        "jump": _channel(False),
                        "boost": _channel(True),
                        "handbrake": _channel(False),
                    }
                ],
                "events": [
                    {
                        "kind": "Dodge",
                        "detail": {"dir": [1.0, 0.0]},
                        "tick": 30,
                        "t": 1.25,
                        "frame_index": 9,
                        "confidence": 1.0,
                        "flags": 0,
                    }
                ],
                "segments": [
                    {
                        "id": 1,
                        "tick_span": [28, 40],
                        "boundary_causes": ["Liftoff", "StreamEdge"],
                        "confidence": 1.0,
                    }
                ],
            }
        ],
        "coverage": {"air_segments": 1},
        "diagnostics": {"warnings": []},
    }

    timelines = mirror_solve_output(raw)

    timeline = timelines["player_0"]
    assert isinstance(timeline.samples[0], InputSample)
    assert isinstance(timeline.samples[0].throttle, ChannelValue)
    assert isinstance(timeline.events[0], SolvedEvent)
    assert timeline.events[0].detail == {"dir": [1.0, 0.0]}
    assert timeline.segments[0].boundary_causes == ("Liftoff", "StreamEdge")
    with pytest.raises(AttributeError):
        timeline.player_id = "mutated"  # type: ignore[misc]


def test_analysis_input_timeline_cache_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    import rlcoach.analysis as analysis_module

    calls = 0

    def fake_solver(frames: list[Frame], header: Header | None = None):
        nonlocal calls
        calls += 1
        return {
            "player_0": input_timeline.InputTimeline(
                player_id="player_0",
                samples=(),
                events=(),
                segments=(),
                coverage={},
                diagnostics={},
            )
        }

    monkeypatch.setattr(analysis_module, "solve_input_timelines", fake_solver)
    getter = analysis_module._make_input_timeline_cache(_frames(), Header())

    assert calls == 0
    assert getter("player_0") is not None
    assert getter("missing") is None
    assert calls == 1


def test_0925_wheel_boundary_counts_and_perf() -> None:
    pytest.importorskip("rlinput_py")
    pytest.importorskip("rlreplay_rust")

    from rlcoach.normalize import build_timeline
    from rlcoach.parser.rust_adapter import RustAdapter

    replay = Path("Replay_files/0925.replay")
    adapter = RustAdapter()
    header = adapter.parse_header(replay)
    network = adapter.parse_network(replay)
    if network is None or not network.frames:
        pytest.skip("Rust replay wheel did not emit network frames")

    frames = build_timeline(header, network.frames)
    start = time.perf_counter()
    timelines = solve_input_timelines(frames, header)
    elapsed = time.perf_counter() - start
    if timelines is None:
        pytest.skip("rlinput_py unavailable")

    first = next(iter(timelines.values()))
    segment_count = sum(len(timeline.segments) for timeline in timelines.values())
    assert segment_count == 858
    assert first.coverage["air_segments"] == 522
    assert sum(len(timeline.events) for timeline in timelines.values()) > 0
    assert elapsed <= 2.0


def _channel(value: float | bool) -> dict[str, object]:
    return {"value": value, "source": "Inferred", "confidence": 0.0, "flags": 0}


def _raise_import(_name: str):
    raise ImportError("missing")
