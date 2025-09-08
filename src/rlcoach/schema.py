"""JSON Schema validation for Rocket League replay reports."""

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft7Validator


def _load_schema() -> dict[str, Any]:
    """Load the replay report JSON schema from file.
    
    Returns:
        The parsed JSON schema dictionary.
        
    Raises:
        FileNotFoundError: If schema file is missing.
        json.JSONDecodeError: If schema file is invalid JSON.
    """
    schema_path = (Path(__file__).parent.parent.parent / 
                   "schemas" / "replay_report.schema.json")

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, encoding='utf-8') as f:
        return json.load(f)


def _create_validator() -> Draft7Validator:
    """Create a Draft-07 validator with format checking enabled.
    
    Returns:
        Configured JSON schema validator.
    """
    schema = _load_schema()

    # Enable format validation for date-time fields
    format_checker = jsonschema.FormatChecker()

    return Draft7Validator(schema, format_checker=format_checker)


def _format_validation_error(error: jsonschema.ValidationError) -> str:
    """Format a validation error into a clear, actionable message.
    
    Args:
        error: The validation error from jsonschema.
        
    Returns:
        Formatted error message with path and context.
    """
    path_str = ""
    if error.absolute_path:
        path_parts = []
        for part in error.absolute_path:
            if isinstance(part, int):
                path_parts.append(f"[{part}]")
            else:
                if path_parts:
                    path_parts.append(f".{part}")
                else:
                    path_parts.append(str(part))
        path_str = f" at path '{'.'.join(path_parts)}'"

    # Format the error message based on the validation failure type
    if error.validator == "required":
        missing_props = error.message.split("'")[1::2]  # Extract property names
        return f"Missing required field(s): {', '.join(missing_props)}{path_str}"

    elif error.validator == "enum":
        allowed_values = list(error.validator_value)
        return (f"Invalid value{path_str}. Allowed values: {allowed_values}. "
                f"Got: {error.instance}")

    elif error.validator == "type":
        expected_type = error.validator_value
        actual_type = type(error.instance).__name__
        return (f"Invalid type{path_str}. Expected {expected_type}, "
                f"got {actual_type}: {error.instance}")

    elif error.validator == "pattern":
        pattern = error.validator_value
        return (f"Value does not match required pattern{path_str}. "
                f"Pattern: {pattern}, Got: {error.instance}")

    elif error.validator == "minimum" or error.validator == "maximum":
        limit = error.validator_value
        op = ">=" if error.validator == "minimum" else "<="
        return f"Value{path_str} must be {op} {limit}. Got: {error.instance}"

    elif error.validator == "additionalProperties":
        return f"Additional properties not allowed{path_str}: {error.message}"

    elif error.validator == "oneOf":
        return (f"Data does not match any of the expected schemas{path_str}. "
                f"This typically means the object is neither a valid success "
                f"report nor a valid error report.")

    else:
        # Fallback to the original error message
        return f"{error.message}{path_str}"


def validate_report(obj: dict[str, Any]) -> None:
    """Validate a replay report object against the JSON schema.
    
    This function validates both success and error report formats according to
    the RocketLeagueReplayReport schema. It provides clear, actionable error 
    messages for validation failures.
    
    Args:
        obj: The replay report dictionary to validate.
        
    Raises:
        jsonschema.ValidationError: If the report is invalid. The error message
            will be formatted to be clear and actionable, including the path
            to the invalid field and expected vs actual values.
        TypeError: If obj is not a dictionary.
        
    Examples:
        >>> # Valid success report
        >>> report = {"replay_id": "abc123", "schema_version": "1.0.0", ...}
        >>> validate_report(report)  # No exception raised
        
        >>> # Valid error report  
        >>> error_report = {"error": "unreadable_replay_file", "details": "CRC failed"}
        >>> validate_report(error_report)  # No exception raised
        
        >>> # Invalid report
        >>> invalid = {"replay_id": 123}  # Wrong type
        >>> validate_report(invalid)  # Raises ValidationError
    """
    if not isinstance(obj, dict):
        raise TypeError(f"Report must be a dictionary, got {type(obj).__name__}")

    validator = _create_validator()

    try:
        validator.validate(obj)
    except jsonschema.ValidationError as e:
        # Re-raise with a more user-friendly message
        formatted_message = _format_validation_error(e)
        raise jsonschema.ValidationError(formatted_message) from e

    # Additional validation for schema_version if present
    if "schema_version" in obj:
        version = obj["schema_version"]
        if not re.match(r"^1\.0\.\d+$", version):
            raise jsonschema.ValidationError(
                f"Invalid schema_version format: {version}. "
                f"Must match pattern ^1.0.\\d+$"
            )


def validate_report_file(file_path: str) -> None:
    """Validate a replay report JSON file against the schema.
    
    Args:
        file_path: Path to the JSON file to validate.
        
    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        jsonschema.ValidationError: If the report is invalid.
    """
    with open(file_path, encoding='utf-8') as f:
        obj = json.load(f)

    validate_report(obj)
