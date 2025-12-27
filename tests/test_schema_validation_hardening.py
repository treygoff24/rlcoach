"""Additional schema validation hardening tests.

These tests assert that jsonschema exposes informative validator metadata
for common failure modes. They complement, not replace, existing tests.
"""

import jsonschema
import pytest

from rlcoach.schema import validate_report


def _get_cause(exc: Exception):
    return getattr(exc, "__cause__", None)


def test_enum_error_has_validator_and_path():
    invalid = {"error": "invalid_error_type", "details": "x"}
    try:
        validate_report(invalid)
    except jsonschema.ValidationError as e:
        cause = _get_cause(e)
        assert cause is not None
        assert cause.validator == "enum"
        # Ensure the error points at the 'error' field
        path = list(getattr(cause, "path", []))
        assert path and path[-1] == "error"
    else:
        pytest.fail("Expected ValidationError was not raised")


def test_type_error_has_validator():
    invalid = {
        "replay_id": 123,  # should be string
        "schema_version": "1.0.0",
        "metadata": {},
        "quality": {"parser": {"name": "x", "version": "1", "parsed_header": True, "parsed_network_data": True}, "warnings": []},
        "teams": {"blue": {"name": "BLUE", "score": 0, "players": []}, "orange": {"name": "ORANGE", "score": 0, "players": []}},
        "players": [],
        "events": {"timeline": [], "goals": [], "demos": [], "kickoffs": [], "boost_pickups": [], "touches": [], "challenges": []},
        "analysis": {"per_team": {"blue": {}, "orange": {}}, "per_player": {}, "coaching_insights": []},
    }

    try:
        validate_report(invalid)
    except jsonschema.ValidationError as e:
        cause = _get_cause(e)
        assert cause is not None
        assert cause.validator in {"type", "required", "oneOf"}
    else:
        pytest.fail("Expected ValidationError was not raised")


def test_schema_version_pattern_has_validator():
    invalid = {
        "replay_id": "abc",
        "schema_version": "2.0.0",  # wrong major
        "metadata": {"engine_build": "x", "playlist": "STANDARD", "map": "DFH_Stadium", "team_size": 3, "match_guid": "g", "started_at_utc": "2025-09-01T00:00:00Z", "duration_seconds": 10},
        "quality": {"parser": {"name": "x", "version": "1", "parsed_header": True, "parsed_network_data": True}, "warnings": []},
        "teams": {"blue": {"name": "BLUE", "score": 0, "players": []}, "orange": {"name": "ORANGE", "score": 0, "players": []}},
        "players": [],
        "events": {"timeline": [], "goals": [], "demos": [], "kickoffs": [], "boost_pickups": [], "touches": [], "challenges": []},
        "analysis": {"per_team": {"blue": {}, "orange": {}}, "per_player": {}, "coaching_insights": []},
    }
    try:
        validate_report(invalid)
    except jsonschema.ValidationError as e:
        cause = _get_cause(e)
        # Either our post-validate check or the schema's pattern triggers
        if cause is not None:
            assert cause.validator in {"pattern", "oneOf"}
        else:
            # Fallback: message should mention schema_version
            assert "schema_version" in str(e)
    else:
        pytest.fail("Expected ValidationError was not raised")


def test_nested_vec3_missing_component_reports_required():
    invalid = {
        "replay_id": "abc",
        "schema_version": "1.0.0",
        "metadata": {"engine_build": "x", "playlist": "STANDARD", "map": "DFH_Stadium", "team_size": 3, "match_guid": "g", "started_at_utc": "2025-09-01T00:00:00Z", "duration_seconds": 10},
        "quality": {"parser": {"name": "x", "version": "1", "parsed_header": True, "parsed_network_data": True}, "warnings": []},
        "teams": {"blue": {"name": "BLUE", "score": 0, "players": ["p1"]}, "orange": {"name": "ORANGE", "score": 0, "players": ["p2"]}},
        "players": [
            {"player_id": "p1", "display_name": "P1", "team": "BLUE", "platform_ids": {}, "camera": {}, "loadout": {}},
            {"player_id": "p2", "display_name": "P2", "team": "ORANGE", "platform_ids": {}, "camera": {}, "loadout": {}},
        ],
        "events": {"timeline": [], "goals": [], "demos": [{"t": 1.0, "attacker": "p1", "victim": "p2", "team_attacker": "BLUE", "team_victim": "ORANGE", "location": {"x": 1, "y": 2}}], "kickoffs": [], "boost_pickups": [], "touches": []},
        "analysis": {"per_team": {"blue": {}, "orange": {}}, "per_player": {}, "coaching_insights": []},
    }
    try:
        validate_report(invalid)
    except jsonschema.ValidationError as e:
        cause = _get_cause(e)
        assert cause is not None
        assert cause.validator in {"required", "type"}
    else:
        pytest.fail("Expected ValidationError was not raised")

