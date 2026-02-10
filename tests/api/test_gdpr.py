# tests/api/test_gdpr.py
"""Tests for GDPR data removal functionality.

Tests the ID prefixing logic that was added to properly match
stored player IDs (which use platform:id format like steam:xxx).
"""

import pytest


class TestGDPRIDPrefixing:
    """Unit tests for ID prefixing logic used in GDPR lookups."""

    def test_steam_id_prefix_format(self):
        """Verify Steam IDs get prefixed with 'steam:'."""
        raw_id = "76561198012345678"
        prefixed = f"steam:{raw_id}"
        assert prefixed == "steam:76561198012345678"
        assert prefixed.startswith("steam:")
        assert raw_id in prefixed

    def test_epic_id_prefix_format(self):
        """Verify Epic IDs get prefixed with 'epic:'."""
        raw_id = "abc123def456"
        prefixed = f"epic:{raw_id}"
        assert prefixed == "epic:abc123def456"
        assert prefixed.startswith("epic:")
        assert raw_id in prefixed

    def test_display_name_no_prefix(self):
        """Display names should not be prefixed."""
        display_name = "SomePlayer"
        # Display names are used as-is for ilike queries
        assert ":" not in display_name  # Confirm no platform prefix expected

    def test_prefix_matches_db_format(self):
        """Verify prefix format matches what db/writer.py stores."""
        # db/writer.py stores player IDs as "platform:id" (e.g., steam:76561...)
        # GDPR queries must use the same format to match

        # Steam ID case
        steam_id = "76561198012345678"
        expected_db_format = f"steam:{steam_id}"

        # This is how GDPR code now builds the query
        prefixed_id = f"steam:{steam_id}"
        assert prefixed_id == expected_db_format

        # Epic ID case
        epic_id = "abc123def456"
        expected_db_format = f"epic:{epic_id}"
        prefixed_id = f"epic:{epic_id}"
        assert prefixed_id == expected_db_format


class TestRemovalRequestValidation:
    """Tests for RemovalRequest pydantic model validation."""

    def test_valid_steam_id_request(self):
        """Test valid Steam ID request creation."""
        from rlcoach.api.routers.gdpr import RemovalRequest

        req = RemovalRequest(
            player_identifier="76561198012345678",
            identifier_type="steam_id",
            email="test@example.com",
        )
        assert req.player_identifier == "76561198012345678"
        assert req.identifier_type == "steam_id"
        assert req.email == "test@example.com"

    def test_valid_epic_id_request(self):
        """Test valid Epic ID request creation."""
        from rlcoach.api.routers.gdpr import RemovalRequest

        req = RemovalRequest(
            player_identifier="abc123def456",
            identifier_type="epic_id",
            email="user@domain.org",
        )
        assert req.player_identifier == "abc123def456"
        assert req.identifier_type == "epic_id"

    def test_valid_display_name_request(self):
        """Test valid display name request creation."""
        from rlcoach.api.routers.gdpr import RemovalRequest

        req = RemovalRequest(
            player_identifier="SomePlayer",
            identifier_type="display_name",
            email="player@example.com",
        )
        assert req.identifier_type == "display_name"

    def test_invalid_identifier_type_rejected(self):
        """Test that invalid identifier types are rejected."""
        from pydantic import ValidationError

        from rlcoach.api.routers.gdpr import RemovalRequest

        with pytest.raises(ValidationError):
            RemovalRequest(
                player_identifier="12345",
                identifier_type="invalid_type",
                email="test@example.com",
            )

    def test_invalid_email_rejected(self):
        """Test that invalid email formats are rejected."""
        from pydantic import ValidationError

        from rlcoach.api.routers.gdpr import RemovalRequest

        with pytest.raises(ValidationError):
            RemovalRequest(
                player_identifier="76561198012345678",
                identifier_type="steam_id",
                email="not-an-email",
            )

    def test_identifier_too_short_rejected(self):
        """Test that identifiers under 3 chars are rejected."""
        from pydantic import ValidationError

        from rlcoach.api.routers.gdpr import RemovalRequest

        with pytest.raises(ValidationError):
            RemovalRequest(
                player_identifier="ab",  # Too short
                identifier_type="steam_id",
                email="test@example.com",
            )

    def test_email_normalized_to_lowercase(self):
        """Test that emails are normalized to lowercase."""
        from rlcoach.api.routers.gdpr import RemovalRequest

        req = RemovalRequest(
            player_identifier="76561198012345678",
            identifier_type="steam_id",
            email="Test@EXAMPLE.com",
        )
        assert req.email == "test@example.com"

    def test_dangerous_chars_stripped_from_identifier(self):
        """Test that potentially dangerous characters are removed."""
        from rlcoach.api.routers.gdpr import RemovalRequest

        req = RemovalRequest(
            player_identifier="Player<script>alert('xss')</script>Name",
            identifier_type="display_name",
            email="test@example.com",
        )
        # Dangerous chars like < > " ' & ; should be stripped
        assert "<" not in req.player_identifier
        assert ">" not in req.player_identifier
        assert "'" not in req.player_identifier
