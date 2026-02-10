"""Tests for offline UI report viewer."""

from __future__ import annotations

import json

from rlcoach import ui


def _sample_report() -> dict:
    return {
        "metadata": {
            "playlist": "DOUBLES",
            "map": "DFH Stadium",
            "team_size": 2,
            "duration_seconds": 300,
            "total_frames": 9000,
            "recorded_frame_hz": 30,
        },
        "teams": {
            "blue": {"score": 2, "players": ["Alice", "Bob"]},
            "orange": {"score": 1, "players": ["Cara", "Dax"]},
        },
        "players": [
            {"player_id": "p1", "display_name": "Alice", "team": "blue"},
            {"player_id": "p2", "display_name": "Bob", "team": "blue"},
        ],
        "analysis": {
            "per_team": {
                "blue": {
                    "fundamentals": {"goals": 2, "shots": 5, "saves": 3},
                    "boost": {"avg_boost": 41.2},
                    "movement": {"avg_speed_kph": 56.3},
                },
                "orange": {
                    "fundamentals": {"goals": 1, "shots": 4, "saves": 2},
                    "boost": {"avg_boost": 35.0},
                    "movement": {"avg_speed_kph": 52.1},
                },
            },
            "per_player": {
                "p1": {
                    "fundamentals": {"goals": 1},
                    "boost": {"avg_boost": 45},
                    "movement": {"avg_speed_kph": 57},
                }
            },
        },
    }


def test_summarize_report_includes_core_sections():
    summary = ui.summarize_report(_sample_report())
    assert "Replay Summary" in summary
    assert "Teams" in summary
    assert "Players" in summary
    assert "Key Metrics" in summary
    assert "Alice [blue]" in summary


def test_summarize_report_with_focus_player_adds_player_section():
    summary = ui.summarize_report(_sample_report(), focus_player="alice")
    assert "Player Focus" in summary
    assert "fundamentals" in summary


def test_cmd_view_success_reads_and_prints(tmp_path, monkeypatch):
    json_path = tmp_path / "report.json"
    json_path.write_text(json.dumps(_sample_report()), encoding="utf-8")

    printed: list[str] = []
    monkeypatch.setattr(ui, "_print", printed.append)

    code = ui.cmd_view(json_path)
    assert code == 0
    assert printed
    assert "Replay Summary" in printed[0]


def test_cmd_view_file_not_found(monkeypatch):
    printed: list[str] = []
    monkeypatch.setattr(ui, "_print", printed.append)

    code = ui.cmd_view("missing.json")
    assert code == 2
    assert "file not found" in printed[0].lower()


def test_cmd_view_invalid_json(tmp_path, monkeypatch):
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")

    printed: list[str] = []
    monkeypatch.setattr(ui, "_print", printed.append)

    code = ui.cmd_view(bad_json)
    assert code == 2
    assert "invalid json" in printed[0].lower()


def test_main_routes_to_view(monkeypatch):
    called = {"path": None, "player": None}

    def fake_cmd_view(path, focus_player=None):
        called["path"] = str(path)
        called["player"] = focus_player
        return 7

    monkeypatch.setattr(ui, "cmd_view", fake_cmd_view)
    code = ui.main(["view", "x.json", "--player", "alice"])
    assert code == 7
    assert called["path"].endswith("x.json")
    assert called["player"] == "alice"
