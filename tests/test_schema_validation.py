"""Tests for JSON Schema validation of replay reports."""

import json
from pathlib import Path

import jsonschema
import pytest

from rlcoach.schema import validate_report, validate_report_file


class TestSchemaValidation:
    """Test suite for replay report schema validation."""

    @pytest.fixture
    def examples_dir(self):
        """Path to examples directory."""
        return Path(__file__).parent.parent / "examples"

    @pytest.fixture
    def success_report(self, examples_dir):
        """Load the success example report."""
        with open(examples_dir / "replay_report.success.json") as f:
            return json.load(f)

    @pytest.fixture
    def error_report(self, examples_dir):
        """Load the error example report."""
        with open(examples_dir / "replay_report.error.json") as f:
            return json.load(f)

    def test_valid_success_report_passes(self, success_report):
        """Test that a valid success report passes validation."""
        # Should not raise any exception
        validate_report(success_report)

    def test_valid_error_report_passes(self, error_report):
        """Test that a valid error report passes validation."""
        # Should not raise any exception
        validate_report(error_report)

    @pytest.mark.parametrize(
        "example_file", ["replay_report.success.json", "replay_report.error.json"]
    )
    def test_example_files_validate(self, examples_dir, example_file):
        """Test both example files validate correctly."""
        file_path = examples_dir / example_file
        # Should not raise any exception
        validate_report_file(str(file_path))

    def test_missing_required_fields_success_report(self):
        """Test validation fails when required fields are missing from success report."""
        invalid_report = {
            "replay_id": "test123",
            "schema_version": "1.0.0",
            # Missing metadata, quality, teams, players, events, analysis
        }

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            validate_report(invalid_report)

        error_msg = str(exc_info.value)
        # Due to oneOf validation, this might show as schema mismatch
        assert (
            "Missing required field" in error_msg
            or "does not match" in error_msg
            or "metadata" in error_msg
            or "quality" in error_msg
        )

    def test_missing_required_fields_error_report(self):
        """Test validation fails when required fields are missing from error report."""
        invalid_report = {
            "error": "unreadable_replay_file"
            # Missing details
        }

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            validate_report(invalid_report)

        error_msg = str(exc_info.value)
        # Due to oneOf validation, this might show as schema mismatch
        assert (
            "Missing required field" in error_msg
            or "details" in error_msg
            or "does not match" in error_msg
        )

    def test_invalid_enum_values(self):
        """Test validation fails for invalid enum values."""
        invalid_report = {
            "error": "invalid_error_type",  # Not in enum
            "details": "Some error details",
        }

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            validate_report(invalid_report)

        error_msg = str(exc_info.value)
        assert "Invalid value" in error_msg or "unreadable_replay_file" in error_msg

    def test_wrong_data_types(self):
        """Test validation fails for wrong data types."""
        invalid_report = {
            "replay_id": 123,  # Should be string
            "schema_version": "1.0.0",
            "metadata": {
                "engine_build": "v2.54",
                "playlist": "STANDARD",
                "map": "DFH_Stadium",
                "team_size": "three",  # Should be integer
                "match_guid": "test",
                "started_at_utc": "2025-09-01T20:04:33Z",
                "duration_seconds": 300,
            },
            "quality": {
                "parser": {
                    "name": "test",
                    "version": "1.0",
                    "parsed_header": True,
                    "parsed_network_data": True,
                },
                "warnings": [],
            },
            "teams": {
                "blue": {"name": "BLUE", "score": 0, "players": []},
                "orange": {"name": "ORANGE", "score": 0, "players": []},
            },
            "players": [],
            "events": {
                "timeline": [],
                "goals": [],
                "demos": [],
                "kickoffs": [],
                "boost_pickups": [],
                "touches": [],
                "challenges": [],
            },
            "analysis": {
                "per_team": {
                    "blue": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                    "orange": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                },
                "per_player": {},
                "coaching_insights": [],
            },
        }

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            validate_report(invalid_report)

        error_msg = str(exc_info.value)
        assert "Invalid type" in error_msg or "Expected" in error_msg

    def test_invalid_schema_version_pattern(self):
        """Test validation fails for invalid schema version patterns."""
        test_cases = [
            "1.0",  # Missing patch version
            "2.0.0",  # Wrong major version
            "1.1.0",  # Wrong minor version
            "1.0.x",  # Non-numeric patch
            "v1.0.0",  # Extra prefix
            "1.0.0.0",  # Too many parts
        ]

        for invalid_version in test_cases:
            invalid_report = {
                "replay_id": "test123",
                "schema_version": invalid_version,
                "metadata": {
                    "engine_build": "v2.54",
                    "playlist": "STANDARD",
                    "map": "DFH_Stadium",
                    "team_size": 3,
                    "match_guid": "test",
                    "started_at_utc": "2025-09-01T20:04:33Z",
                    "duration_seconds": 300,
                },
                "quality": {
                    "parser": {
                        "name": "test",
                        "version": "1.0",
                        "parsed_header": True,
                        "parsed_network_data": True,
                    },
                    "warnings": [],
                },
                "teams": {
                    "blue": {"name": "BLUE", "score": 0, "players": []},
                    "orange": {"name": "ORANGE", "score": 0, "players": []},
                },
                "players": [],
                "events": {
                    "timeline": [],
                    "goals": [],
                    "demos": [],
                    "kickoffs": [],
                    "boost_pickups": [],
                    "touches": [],
                    "challenges": [],
                },
                "analysis": {
                    "per_team": {
                        "blue": {
                            "fundamentals": {
                                "goals": 0,
                                "assists": 0,
                                "shots": 0,
                                "saves": 0,
                                "demos_inflicted": 0,
                                "demos_taken": 0,
                                "score": 0,
                                "shooting_percentage": 0,
                            },
                            "boost": {
                                "bpm": 0,
                                "bcpm": 0,
                                "avg_boost": 0,
                                "time_zero_boost_s": 0,
                                "time_full_boost_s": 0,
                                "boost_collected": 0,
                                "boost_stolen": 0,
                                "big_pads": 0,
                                "small_pads": 0,
                                "stolen_big_pads": 0,
                                "stolen_small_pads": 0,
                                "overfill": 0,
                                "waste": 0,
                            },
                            "movement": {
                                "avg_speed_kph": 0,
                                "distance_km": 0,
                                "max_speed_kph": 0,
                                "time_slow_s": 0,
                                "time_boost_speed_s": 0,
                                "time_supersonic_s": 0,
                                "time_ground_s": 0,
                                "time_low_air_s": 0,
                                "time_high_air_s": 0,
                                "powerslide_count": 0,
                                "powerslide_duration_s": 0,
                                "aerial_count": 0,
                                "aerial_time_s": 0,
                            },
                            "positioning": {
                                "time_offensive_half_s": 0,
                                "time_defensive_half_s": 0,
                                "time_offensive_third_s": 0,
                                "time_middle_third_s": 0,
                                "time_defensive_third_s": 0,
                                "behind_ball_pct": 0,
                                "ahead_ball_pct": 0,
                                "avg_distance_to_ball_m": 0,
                                "avg_distance_to_teammate_m": 0,
                                "first_man_pct": 0,
                                "second_man_pct": 0,
                                "third_man_pct": 0,
                            },
                            "passing": {
                                "passes_completed": 0,
                                "passes_attempted": 0,
                                "passes_received": 0,
                                "turnovers": 0,
                                "give_and_go_count": 0,
                                "possession_time_s": 0,
                            },
                            "challenges": {
                                "contests": 0,
                                "wins": 0,
                                "losses": 0,
                                "neutral": 0,
                                "first_to_ball_pct": 0,
                                "challenge_depth_m": 0,
                                "risk_index_avg": 0,
                            },
                            "kickoffs": {
                                "count": 0,
                                "first_possession": 0,
                                "neutral": 0,
                                "goals_for": 0,
                                "goals_against": 0,
                                "avg_time_to_first_touch_s": 0,
                                "approach_types": {
                                    "STANDARD": 0,
                                    "SPEEDFLIP": 0,
                                    "FAKE": 0,
                                    "DELAY": 0,
                                    "UNKNOWN": 0,
                                },
                            },
                        },
                        "orange": {
                            "fundamentals": {
                                "goals": 0,
                                "assists": 0,
                                "shots": 0,
                                "saves": 0,
                                "demos_inflicted": 0,
                                "demos_taken": 0,
                                "score": 0,
                                "shooting_percentage": 0,
                            },
                            "boost": {
                                "bpm": 0,
                                "bcpm": 0,
                                "avg_boost": 0,
                                "time_zero_boost_s": 0,
                                "time_full_boost_s": 0,
                                "boost_collected": 0,
                                "boost_stolen": 0,
                                "big_pads": 0,
                                "small_pads": 0,
                                "stolen_big_pads": 0,
                                "stolen_small_pads": 0,
                                "overfill": 0,
                                "waste": 0,
                            },
                            "movement": {
                                "avg_speed_kph": 0,
                                "distance_km": 0,
                                "max_speed_kph": 0,
                                "time_slow_s": 0,
                                "time_boost_speed_s": 0,
                                "time_supersonic_s": 0,
                                "time_ground_s": 0,
                                "time_low_air_s": 0,
                                "time_high_air_s": 0,
                                "powerslide_count": 0,
                                "powerslide_duration_s": 0,
                                "aerial_count": 0,
                                "aerial_time_s": 0,
                            },
                            "positioning": {
                                "time_offensive_half_s": 0,
                                "time_defensive_half_s": 0,
                                "time_offensive_third_s": 0,
                                "time_middle_third_s": 0,
                                "time_defensive_third_s": 0,
                                "behind_ball_pct": 0,
                                "ahead_ball_pct": 0,
                                "avg_distance_to_ball_m": 0,
                                "avg_distance_to_teammate_m": 0,
                                "first_man_pct": 0,
                                "second_man_pct": 0,
                                "third_man_pct": 0,
                            },
                            "passing": {
                                "passes_completed": 0,
                                "passes_attempted": 0,
                                "passes_received": 0,
                                "turnovers": 0,
                                "give_and_go_count": 0,
                                "possession_time_s": 0,
                            },
                            "challenges": {
                                "contests": 0,
                                "wins": 0,
                                "losses": 0,
                                "neutral": 0,
                                "first_to_ball_pct": 0,
                                "challenge_depth_m": 0,
                                "risk_index_avg": 0,
                            },
                            "kickoffs": {
                                "count": 0,
                                "first_possession": 0,
                                "neutral": 0,
                                "goals_for": 0,
                                "goals_against": 0,
                                "avg_time_to_first_touch_s": 0,
                                "approach_types": {
                                    "STANDARD": 0,
                                    "SPEEDFLIP": 0,
                                    "FAKE": 0,
                                    "DELAY": 0,
                                    "UNKNOWN": 0,
                                },
                            },
                        },
                    },
                    "per_player": {},
                    "coaching_insights": [],
                },
            }

            with pytest.raises(jsonschema.ValidationError) as exc_info:
                validate_report(invalid_report)

            error_msg = str(exc_info.value)
            assert (
                "pattern" in error_msg.lower()
                or "schema_version" in error_msg
                or "1.0" in error_msg
            ), f"Failed for version {invalid_version}: {error_msg}"

    def test_additional_properties_not_allowed(self):
        """Test validation fails when additional properties are present."""
        # Create a minimal valid success report and add an extra property
        valid_report = {
            "replay_id": "test123",
            "schema_version": "1.0.0",
            "metadata": {
                "engine_build": "v2.54",
                "playlist": "STANDARD",
                "map": "DFH_Stadium",
                "team_size": 3,
                "match_guid": "test",
                "started_at_utc": "2025-09-01T20:04:33Z",
                "duration_seconds": 300,
            },
            "quality": {
                "parser": {
                    "name": "test",
                    "version": "1.0",
                    "parsed_header": True,
                    "parsed_network_data": True,
                },
                "warnings": [],
            },
            "teams": {
                "blue": {"name": "BLUE", "score": 0, "players": ["p1"]},
                "orange": {"name": "ORANGE", "score": 0, "players": []},
            },
            "players": [
                {
                    "player_id": "p1",
                    "display_name": "Player1",
                    "team": "BLUE",
                    "platform_ids": {},
                    "camera": {},
                    "loadout": {},
                }
            ],
            "events": {
                "timeline": [],
                "goals": [],
                "demos": [],
                "kickoffs": [],
                "boost_pickups": [],
                "touches": [],
                "challenges": [],
            },
            "analysis": {
                "per_team": {
                    "blue": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                    "orange": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                },
                "per_player": {},
                "coaching_insights": [],
            },
            "extra_field": "not allowed",  # This should cause validation to fail
        }

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            validate_report(valid_report)

        error_msg = str(exc_info.value)
        assert (
            "Additional properties" in error_msg
            or "not allowed" in error_msg
            or "extra_field" in error_msg
        )

    def test_invalid_nested_structures(self):
        """Test validation fails for invalid nested structures like malformed vec3."""
        # Test with malformed vec3 in a success report
        malformed_success = {
            "replay_id": "test123",
            "schema_version": "1.0.0",
            "metadata": {
                "engine_build": "v2.54",
                "playlist": "STANDARD",
                "map": "DFH_Stadium",
                "team_size": 3,
                "match_guid": "test",
                "started_at_utc": "2025-09-01T20:04:33Z",
                "duration_seconds": 300,
            },
            "quality": {
                "parser": {
                    "name": "test",
                    "version": "1.0",
                    "parsed_header": True,
                    "parsed_network_data": True,
                },
                "warnings": [],
            },
            "teams": {
                "blue": {"name": "BLUE", "score": 0, "players": ["p1"]},
                "orange": {"name": "ORANGE", "score": 0, "players": ["p2"]},
            },
            "players": [
                {
                    "player_id": "p1",
                    "display_name": "Player1",
                    "team": "BLUE",
                    "platform_ids": {},
                    "camera": {},
                    "loadout": {},
                },
                {
                    "player_id": "p2",
                    "display_name": "Player2",
                    "team": "ORANGE",
                    "platform_ids": {},
                    "camera": {},
                    "loadout": {},
                },
            ],
            "events": {
                "timeline": [],
                "goals": [],
                "demos": [
                    {
                        "t": 10.0,
                        "attacker": "p1",
                        "victim": "p2",
                        "team_attacker": "BLUE",
                        "team_victim": "ORANGE",
                        "location": {
                            "x": 100,
                            "y": 200,
                            # Missing required 'z' field
                        },
                    }
                ],
                "kickoffs": [],
                "boost_pickups": [],
                "touches": [],
                "challenges": [],
            },
            "analysis": {
                "per_team": {
                    "blue": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                    "orange": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                },
                "per_player": {},
                "coaching_insights": [],
            },
        }

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            validate_report(malformed_success)

        error_msg = str(exc_info.value)
        assert "Missing required field" in error_msg or "'z'" in error_msg

    def test_boundary_values(self):
        """Test validation with boundary values."""
        # Test minimum/maximum constraints
        invalid_report = {
            "replay_id": "test123",
            "schema_version": "1.0.0",
            "metadata": {
                "engine_build": "v2.54",
                "playlist": "STANDARD",
                "map": "DFH_Stadium",
                "team_size": 5,  # Maximum is 4
                "match_guid": "test",
                "started_at_utc": "2025-09-01T20:04:33Z",
                "duration_seconds": 300,
            },
            "quality": {
                "parser": {
                    "name": "test",
                    "version": "1.0",
                    "parsed_header": True,
                    "parsed_network_data": True,
                },
                "warnings": [],
            },
            "teams": {
                "blue": {"name": "BLUE", "score": 0, "players": []},
                "orange": {"name": "ORANGE", "score": 0, "players": []},
            },
            "players": [],
            "events": {
                "timeline": [],
                "goals": [],
                "demos": [],
                "kickoffs": [],
                "boost_pickups": [],
                "touches": [],
                "challenges": [],
            },
            "analysis": {
                "per_team": {
                    "blue": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                    "orange": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                },
                "per_player": {},
                "coaching_insights": [],
            },
        }

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            validate_report(invalid_report)

        error_msg = str(exc_info.value)
        assert (
            "maximum" in error_msg.lower()
            or "must be" in error_msg.lower()
            or "team_size" in error_msg
        )

    def test_empty_arrays_allowed(self):
        """Test that empty arrays are allowed where appropriate."""
        # Create a valid report with empty event arrays
        report_with_empty_arrays = {
            "replay_id": "test123",
            "schema_version": "1.0.0",
            "metadata": {
                "engine_build": "v2.54",
                "playlist": "STANDARD",
                "map": "DFH_Stadium",
                "team_size": 3,
                "match_guid": "test",
                "started_at_utc": "2025-09-01T20:04:33Z",
                "duration_seconds": 300,
            },
            "quality": {
                "parser": {
                    "name": "test",
                    "version": "1.0",
                    "parsed_header": True,
                    "parsed_network_data": True,
                },
                "warnings": [],
            },
            "teams": {
                "blue": {"name": "BLUE", "score": 0, "players": ["p1"]},
                "orange": {"name": "ORANGE", "score": 0, "players": []},
            },
            "players": [
                {
                    "player_id": "p1",
                    "display_name": "Player1",
                    "team": "BLUE",
                    "platform_ids": {},
                    "camera": {},
                    "loadout": {},
                }
            ],
            "events": {
                "timeline": [],
                "goals": [],
                "demos": [],
                "kickoffs": [],
                "boost_pickups": [],
                "touches": [],
                "challenges": [],
            },
            "analysis": {
                "per_team": {
                    "blue": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                    "orange": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                },
                "per_player": {},
                "coaching_insights": [],
            },
        }

        # Should not raise any exception
        validate_report(report_with_empty_arrays)

    def test_null_handling(self):
        """Test proper handling of null values where allowed."""
        valid_report = {
            "replay_id": "test123",
            "schema_version": "1.0.0",
            "metadata": {
                "engine_build": "v2.54",
                "playlist": "STANDARD",
                "map": "DFH_Stadium",
                "team_size": 3,
                "match_guid": "test",
                "started_at_utc": "2025-09-01T20:04:33Z",
                "duration_seconds": 300,
            },
            "quality": {
                "parser": {
                    "name": "test",
                    "version": "1.0",
                    "parsed_header": True,
                    "parsed_network_data": True,
                },
                "warnings": [],
            },
            "teams": {
                "blue": {"name": "BLUE", "score": 0, "players": ["p1"]},
                "orange": {"name": "ORANGE", "score": 0, "players": []},
            },
            "players": [
                {
                    "player_id": "p1",
                    "display_name": "Player1",
                    "team": "BLUE",
                    "platform_ids": {},
                    "camera": {},
                    "loadout": {},
                }
            ],
            "events": {
                "timeline": [],
                "goals": [
                    {
                        "t": 10.0,
                        "frame": 300,
                        "scorer": "p1",
                        "team": "BLUE",
                        "assist": None,  # Null is allowed for assist
                        "shot_speed_kph": 100.0,
                        "distance_m": 20.0,
                        "on_target": True,
                        "tickmark_lead_seconds": 1.0,
                    }
                ],
                "demos": [],
                "kickoffs": [],
                "boost_pickups": [],
                "touches": [],
                "challenges": [],
            },
            "analysis": {
                "per_team": {
                    "blue": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                    "orange": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                },
                "per_player": {},
                "coaching_insights": [],
            },
        }

        # Should not raise any exception
        validate_report(valid_report)

    def test_non_dict_input_raises_type_error(self):
        """Test that non-dictionary input raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            validate_report("not a dict")

        assert "must be a dictionary" in str(exc_info.value)

        with pytest.raises(TypeError) as exc_info:
            validate_report(123)

        assert "must be a dictionary" in str(exc_info.value)

    def test_file_not_found_error(self):
        """Test that validating non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            validate_report_file("nonexistent_file.json")

    def test_malformed_json_file_error(self, tmp_path):
        """Test that validating malformed JSON file raises JSONDecodeError."""
        bad_json_file = tmp_path / "bad.json"
        bad_json_file.write_text("{ invalid json")

        with pytest.raises(json.JSONDecodeError):
            validate_report_file(str(bad_json_file))

    def test_coordinate_reference_constants(self):
        """Test that coordinate reference constants are enforced."""
        invalid_report = {
            "replay_id": "test123",
            "schema_version": "1.0.0",
            "metadata": {
                "engine_build": "v2.54",
                "playlist": "STANDARD",
                "map": "DFH_Stadium",
                "team_size": 3,
                "match_guid": "test",
                "started_at_utc": "2025-09-01T20:04:33Z",
                "duration_seconds": 300,
                "coordinate_reference": {
                    "side_wall_x": 4000,  # Should be exactly 4096
                    "back_wall_y": 5120,
                    "ceiling_z": 2044,
                },
            },
            "quality": {
                "parser": {
                    "name": "test",
                    "version": "1.0",
                    "parsed_header": True,
                    "parsed_network_data": True,
                },
                "warnings": [],
            },
            "teams": {
                "blue": {"name": "BLUE", "score": 0, "players": []},
                "orange": {"name": "ORANGE", "score": 0, "players": []},
            },
            "players": [],
            "events": {
                "timeline": [],
                "goals": [],
                "demos": [],
                "kickoffs": [],
                "boost_pickups": [],
                "touches": [],
                "challenges": [],
            },
            "analysis": {
                "per_team": {
                    "blue": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                    "orange": {
                        "fundamentals": {
                            "goals": 0,
                            "assists": 0,
                            "shots": 0,
                            "saves": 0,
                            "demos_inflicted": 0,
                            "demos_taken": 0,
                            "score": 0,
                            "shooting_percentage": 0,
                        },
                        "boost": {
                            "bpm": 0,
                            "bcpm": 0,
                            "avg_boost": 0,
                            "time_zero_boost_s": 0,
                            "time_full_boost_s": 0,
                            "boost_collected": 0,
                            "boost_stolen": 0,
                            "big_pads": 0,
                            "small_pads": 0,
                            "stolen_big_pads": 0,
                            "stolen_small_pads": 0,
                            "overfill": 0,
                            "waste": 0,
                        },
                        "movement": {
                            "avg_speed_kph": 0,
                            "distance_km": 0,
                            "max_speed_kph": 0,
                            "time_slow_s": 0,
                            "time_boost_speed_s": 0,
                            "time_supersonic_s": 0,
                            "time_ground_s": 0,
                            "time_low_air_s": 0,
                            "time_high_air_s": 0,
                            "powerslide_count": 0,
                            "powerslide_duration_s": 0,
                            "aerial_count": 0,
                            "aerial_time_s": 0,
                        },
                        "positioning": {
                            "time_offensive_half_s": 0,
                            "time_defensive_half_s": 0,
                            "time_offensive_third_s": 0,
                            "time_middle_third_s": 0,
                            "time_defensive_third_s": 0,
                            "behind_ball_pct": 0,
                            "ahead_ball_pct": 0,
                            "avg_distance_to_ball_m": 0,
                            "avg_distance_to_teammate_m": 0,
                            "first_man_pct": 0,
                            "second_man_pct": 0,
                            "third_man_pct": 0,
                        },
                        "passing": {
                            "passes_completed": 0,
                            "passes_attempted": 0,
                            "passes_received": 0,
                            "turnovers": 0,
                            "give_and_go_count": 0,
                            "possession_time_s": 0,
                        },
                        "challenges": {
                            "contests": 0,
                            "wins": 0,
                            "losses": 0,
                            "neutral": 0,
                            "first_to_ball_pct": 0,
                            "challenge_depth_m": 0,
                            "risk_index_avg": 0,
                        },
                        "kickoffs": {
                            "count": 0,
                            "first_possession": 0,
                            "neutral": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "avg_time_to_first_touch_s": 0,
                            "approach_types": {
                                "STANDARD": 0,
                                "SPEEDFLIP": 0,
                                "FAKE": 0,
                                "DELAY": 0,
                                "UNKNOWN": 0,
                            },
                        },
                    },
                },
                "per_player": {},
                "coaching_insights": [],
            },
        }

        with pytest.raises(jsonschema.ValidationError) as exc_info:
            validate_report(invalid_report)

        error_msg = str(exc_info.value)
        assert (
            "4096" in error_msg
            or "const" in error_msg.lower()
            or "side_wall_x" in error_msg
        )

    @pytest.mark.parametrize(
        "diagnostics",
        [
            {
                "status": "degraded",
                "error_code": "boxcars_network_error",
                "error_detail": "unknown attributes for object",
                "frames_emitted": 0,
            },
            {
                "status": "unavailable",
                "error_code": "network_data_unavailable",
                "error_detail": "network parser did not emit frames",
                "frames_emitted": None,
            },
        ],
    )
    def test_quality_parser_supports_network_diagnostics(
        self, success_report, diagnostics
    ):
        """Test parser quality accepts explicit network diagnostics object."""
        report = json.loads(json.dumps(success_report))
        report["quality"]["parser"]["network_diagnostics"] = diagnostics
        validate_report(report)
