"""Version management for rlcoach schema and package."""

# Schema version follows semver: MAJOR.MINOR.PATCH
# MAJOR: Breaking changes to schema structure
# MINOR: New fields added (backward compatible)
# PATCH: Bug fixes and clarifications
SCHEMA_VERSION = (
    "1.0.1"  # Bumped for boost key renames (amount_collected -> boost_collected, etc.)
)

# Package version
PACKAGE_VERSION = "0.1.0"


def get_schema_version() -> str:
    """Get the current schema version."""
    return SCHEMA_VERSION


def get_package_version() -> str:
    """Get the current package version."""
    return PACKAGE_VERSION


def is_schema_compatible(version: str) -> bool:
    """Check if a schema version is compatible with current version.

    Args:
        version: Schema version to check (e.g., "1.0.0")

    Returns:
        True if compatible (same major version)
    """
    try:
        parts = version.split(".")
        current_parts = SCHEMA_VERSION.split(".")

        if len(parts) != 3 or len(current_parts) != 3:
            return False

        # Same major version means compatible
        return parts[0] == current_parts[0]

    except (ValueError, IndexError):
        return False
