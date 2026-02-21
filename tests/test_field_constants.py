"""Tests for field_constants module.

Verifies that FieldConstants and BOOST_PAD_TABLE expose correct pad metadata
including positions, radii, and pad_side classifications consistent with
the canonical JSON dataset.
"""

from __future__ import annotations

import pytest

from rlcoach.field_constants import (
    BOOST_PAD_TABLE,
    FIELD,
    BoostPad,
    FieldConstants,
    Vec3,
    find_big_pad_blue_corner,
    find_big_pad_orange_corner,
    find_small_pad_blue_side,
    find_small_pad_neutral,
    find_small_pad_orange_side,
)


class TestBoostPadTable:
    def test_total_pad_count(self) -> None:
        assert len(BOOST_PAD_TABLE) == 34

    def test_big_pad_count(self) -> None:
        big = [p for p in BOOST_PAD_TABLE if p.is_big]
        assert len(big) == 6

    def test_small_pad_count(self) -> None:
        small = [p for p in BOOST_PAD_TABLE if not p.is_big]
        assert len(small) == 28

    def test_unique_pad_ids(self) -> None:
        ids = [p.pad_id for p in BOOST_PAD_TABLE]
        assert len(ids) == len(set(ids))
        assert set(ids) == set(range(34))

    def test_pad_side_field_present(self) -> None:
        for pad in BOOST_PAD_TABLE:
            assert pad.pad_side in {"blue", "orange", "mid"}, (
                f"Pad {pad.pad_id} has invalid pad_side '{pad.pad_side}'"
            )

    def test_all_three_sides_represented(self) -> None:
        sides = {p.pad_side for p in BOOST_PAD_TABLE}
        assert sides == {"blue", "orange", "mid"}

    def test_big_pads_not_mid(self) -> None:
        for pad in BOOST_PAD_TABLE:
            if pad.is_big:
                assert pad.pad_side != "mid", (
                    f"Big pad {pad.pad_id} wrongly classified as mid"
                )

    def test_big_pad_radius(self) -> None:
        for pad in BOOST_PAD_TABLE:
            if pad.is_big:
                assert pad.radius == FieldConstants.BIG_BOOST_RADIUS

    def test_small_pad_radius(self) -> None:
        for pad in BOOST_PAD_TABLE:
            if not pad.is_big:
                assert pad.radius == FieldConstants.SMALL_BOOST_RADIUS

    def test_blue_pads_in_blue_half(self) -> None:
        for pad in BOOST_PAD_TABLE:
            if pad.pad_side == "blue":
                assert pad.position.y < 0, (
                    f"Blue pad {pad.pad_id} has y={pad.position.y}"
                )

    def test_orange_pads_in_orange_half(self) -> None:
        for pad in BOOST_PAD_TABLE:
            if pad.pad_side == "orange":
                assert pad.position.y > 0, (
                    f"Orange pad {pad.pad_id} has y={pad.position.y}"
                )

    def test_mid_pads_within_centre_band(self) -> None:
        for pad in BOOST_PAD_TABLE:
            if pad.pad_side == "mid":
                assert abs(pad.position.y) <= 2000, (
                    f"Mid pad {pad.pad_id} has |y|={abs(pad.position.y)} > 2000"
                )


class TestBoostPadDataclass:
    def test_immutable(self) -> None:
        pad = BOOST_PAD_TABLE[0]
        with pytest.raises((AttributeError, TypeError)):
            pad.pad_id = 999  # type: ignore[misc]

    def test_pad_side_default(self) -> None:
        p = BoostPad(pad_id=0, position=Vec3(0, 0, 0), is_big=False, radius=170.0)
        assert p.pad_side == "mid"

    def test_pad_side_explicit(self) -> None:
        p = BoostPad(
            pad_id=1,
            position=Vec3(0, -4608, 73),
            is_big=True,
            radius=250.0,
            pad_side="blue",
        )
        assert p.pad_side == "blue"


class TestFieldHelpers:
    def test_find_big_pad_blue_corner(self) -> None:
        pad = find_big_pad_blue_corner()
        assert pad.is_big
        assert pad.position.y < 0

    def test_find_big_pad_orange_corner(self) -> None:
        pad = find_big_pad_orange_corner()
        assert pad.is_big
        assert pad.position.y > 0

    def test_find_small_pad_neutral(self) -> None:
        pad = find_small_pad_neutral()
        assert not pad.is_big
        assert abs(pad.position.y) < 1500

    def test_find_small_pad_blue_side(self) -> None:
        pad = find_small_pad_blue_side()
        assert not pad.is_big
        assert pad.position.y < -2000

    def test_find_small_pad_orange_side(self) -> None:
        pad = find_small_pad_orange_side()
        assert not pad.is_big
        assert pad.position.y > 2000


class TestFieldConstants:
    def test_field_boundaries(self) -> None:
        assert FieldConstants.SIDE_WALL_X == 4096.0
        assert FieldConstants.BACK_WALL_Y == 5120.0

    def test_is_in_bounds_centre(self) -> None:
        assert FIELD.is_in_bounds(Vec3(0.0, 0.0, 100.0))

    def test_is_in_bounds_outside(self) -> None:
        assert not FIELD.is_in_bounds(Vec3(5000.0, 0.0, 100.0))

    def test_get_field_half(self) -> None:
        assert FIELD.get_field_half(Vec3(0.0, -1000.0, 0.0)) == "blue"
        assert FIELD.get_field_half(Vec3(0.0, 1000.0, 0.0)) == "orange"

    def test_get_field_third(self) -> None:
        assert FIELD.get_field_third(Vec3(0.0, -2000.0, 0.0)) == "defensive"
        assert FIELD.get_field_third(Vec3(0.0, 0.0, 0.0)) == "neutral"
        assert FIELD.get_field_third(Vec3(0.0, 2000.0, 0.0)) == "offensive"

    def test_boost_pads_attribute(self) -> None:
        assert hasattr(FieldConstants, "BOOST_PADS")
        assert len(FieldConstants.BOOST_PADS) == 34

    def test_boost_pads_have_pad_side(self) -> None:
        for pad in FieldConstants.BOOST_PADS:
            assert hasattr(pad, "pad_side")
            assert pad.pad_side in {"blue", "orange", "mid"}
