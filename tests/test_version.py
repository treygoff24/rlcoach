"""Tests for version helpers."""

from rlcoach import version


def test_version_getters_return_expected_values():
    assert version.get_schema_version() == version.SCHEMA_VERSION
    assert version.get_package_version() == version.PACKAGE_VERSION


def test_schema_compatibility_checks_major_version_only():
    assert version.is_schema_compatible("1.0.0") is True
    assert version.is_schema_compatible("1.9.9") is True
    assert version.is_schema_compatible("2.0.0") is False
    assert version.is_schema_compatible("1.0") is False
    assert version.is_schema_compatible("invalid") is False
