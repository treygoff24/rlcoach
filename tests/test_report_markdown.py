"""Tests for the Markdown report composer."""

import json
from pathlib import Path

from rlcoach import report_markdown

FIXTURE_DIR = Path(__file__).parent / "goldens"


def _load_report(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def _load_markdown(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.md").read_text()


def _minimal_report() -> dict:
    return {
        "replay_id": "replay-1",
        "source_file": "/tmp/replay.replay",
        "schema_version": "test-schema",
        "generated_at_utc": "2026-04-09T12:00:00Z",
        "metadata": {
            "map": "DFH Stadium",
            "playlist": "STANDARD",
            "team_size": 1,
            "duration_seconds": 300.0,
            "recorded_frame_hz": 30.0,
            "total_frames": 9000,
            "overtime": False,
            "engine_build": "123",
            "match_guid": "match-guid",
            "mutators": {},
            "coordinate_reference": {
                "side_wall_x": 4096.0,
                "back_wall_y": 5120.0,
                "ceiling_z": 2044.0,
            },
        },
        "quality": {
            "parser": {
                "name": "rust",
                "version": "1.0",
                "parsed_header": True,
                "parsed_network_data": True,
                "crc_checked": True,
            },
            "warnings": [],
        },
        "teams": {
            "blue": {"name": "BLUE", "score": 1, "players": ["blue-1"]},
            "orange": {"name": "ORANGE", "score": 0, "players": ["orange-1"]},
        },
        "players": [
            {
                "player_id": "blue-1",
                "display_name": "Blue One",
                "team": "BLUE",
                "platform_ids": {},
                "camera": {},
                "loadout": {},
            },
            {
                "player_id": "orange-1",
                "display_name": "Orange One",
                "team": "ORANGE",
                "platform_ids": {},
                "camera": {},
                "loadout": {},
            },
        ],
        "analysis": {
            "per_team": {"blue": {"mechanics": {}}, "orange": {"mechanics": {}}},
            "per_player": {
                "blue-1": {"mechanics": {}},
                "orange-1": {"mechanics": {}},
            },
            "coaching_insights": [],
        },
        "events": {
            "timeline": [],
            "goals": [],
            "demos": [],
            "kickoffs": [],
            "boost_pickups": [],
            "touches": [],
            "challenges": [],
        },
    }


def test_render_markdown_matches_golden_synthetic() -> None:
    report = _load_report("synthetic_small")
    expected = _load_markdown("synthetic_small")
    actual = report_markdown.render_markdown(report)
    assert actual == expected


def test_render_markdown_matches_golden_header_only() -> None:
    report = _load_report("header_only")
    expected = _load_markdown("header_only")
    actual = report_markdown.render_markdown(report)
    assert actual == expected


def test_render_markdown_handles_error_payload() -> None:
    error_report = {"error": "unreadable_replay_file", "details": "CRC mismatch"}
    markdown = report_markdown.render_markdown(error_report)
    assert "## Error Summary" in markdown
    assert "CRC mismatch" in markdown
    assert "unreadable_replay_file" in markdown


def test_render_markdown_surfaces_parser_network_diagnostics_and_scorecard() -> None:
    report = _minimal_report()
    report["quality"]["parser"]["network_diagnostics"] = {
        "status": "degraded",
        "error_code": "boxcars_network_error",
        "error_detail": "unknown attributes for object",
        "frames_emitted": 12,
        "attempted_backends": ["boxcars", "legacy"],
    }
    report["quality"]["parser"]["scorecard"] = {
        "usable_network_parse": False,
        "non_empty_player_frame_coverage": 0.25,
        "player_identity_coverage": 0.5,
        "network_frame_count": 12,
        "non_empty_player_frames": 3,
        "players_with_identity": 1,
        "expected_players": 2,
    }

    markdown = report_markdown.render_markdown(report)

    assert "### Network Diagnostics" in markdown
    assert "boxcars_network_error" in markdown
    assert "boxcars, legacy" in markdown
    assert "### Parser Scorecard" in markdown
    assert "Usable Network Parse" in markdown
    assert "0.25" in markdown
    assert "Expected Players" in markdown


def test_render_markdown_surfaces_unavailable_parser_context() -> None:
    report = _minimal_report()
    report["quality"]["parser"]["parsed_network_data"] = False
    report["quality"]["parser"]["network_diagnostics"] = {
        "status": "unavailable",
        "error_code": "network_data_unavailable",
        "error_detail": "network parser did not emit frames",
        "frames_emitted": 0,
        "attempted_backends": [],
    }

    markdown = report_markdown.render_markdown(report)

    assert "### Network Diagnostics" in markdown
    assert "unavailable" in markdown
    assert "network_data_unavailable" in markdown
    assert "network parser did not emit frames" in markdown


def test_render_markdown_surfaces_advanced_team_and_player_mechanics() -> None:
    report = _minimal_report()
    report["analysis"]["per_team"]["blue"]["mechanics"] = {
        "total_flips": 1,
        "total_aerials": 2,
        "total_wavedashes": 3,
        "total_halfflips": 4,
        "total_speedflips": 5,
        "total_flip_cancels": 6,
        "total_fast_aerials": 7,
        "total_flip_resets": 8,
        "total_dribbles": 9,
        "total_flicks": 10,
        "total_ceiling_shots": 11,
        "total_ground_pinches": 12,
        "total_double_touches": 13,
        "total_redirects": 14,
        "total_stalls": 15,
        "total_skims": 16,
        "total_psychos": 17,
    }
    report["analysis"]["per_team"]["orange"]["mechanics"] = dict.fromkeys(
        report["analysis"]["per_team"]["blue"]["mechanics"], 0
    )
    report["analysis"]["per_player"]["blue-1"]["mechanics"] = {
        "jump_count": 1,
        "double_jump_count": 2,
        "flip_count": 3,
        "wavedash_count": 4,
        "aerial_count": 5,
        "halfflip_count": 6,
        "speedflip_count": 7,
        "flip_cancel_count": 8,
        "fast_aerial_count": 9,
        "flip_reset_count": 10,
        "air_roll_count": 11,
        "air_roll_total_time_s": 12.5,
        "dribble_count": 13,
        "dribble_total_time_s": 14.5,
        "flick_count": 15,
        "musty_flick_count": 16,
        "ceiling_shot_count": 17,
        "power_slide_count": 18,
        "power_slide_total_time_s": 19.5,
        "ground_pinch_count": 20,
        "double_touch_count": 21,
        "redirect_count": 22,
        "stall_count": 23,
        "skim_count": 24,
        "psycho_count": 25,
        "total_mechanics": 299,
    }

    markdown = report_markdown.render_markdown(report)

    assert "Total Fast Aerials" in markdown
    assert "Total Flip Resets" in markdown
    assert "Total Skims" in markdown
    assert "Total Psychos" in markdown
    assert "Fast Aerials" in markdown
    assert "Air Rolls" in markdown
    assert "Air Roll Time (s)" in markdown
    assert "Musty Flicks" in markdown
    assert "Power Slides" in markdown
    assert "Power Slide Time (s)" in markdown
    assert "Skims" in markdown
    assert "Psychos" in markdown
