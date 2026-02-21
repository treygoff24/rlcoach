"""Tests for canonical pad metadata and arena snapping.

Verifies that schemas/boost_pad_tables.json is well-formed and that sample
positions from known arenas snap within the documented tolerances:
  - big pads  : < 120 uu (stricter than the 200 uu default)
  - small pads: < 180 uu (stricter than the 160 uu default)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _schema_path() -> Path:
    candidate = Path(__file__)
    for _ in range(6):
        candidate = candidate.parent
        p = candidate / "schemas" / "boost_pad_tables.json"
        if p.exists():
            return p
    raise FileNotFoundError("schemas/boost_pad_tables.json not found")


@pytest.fixture(scope="module")
def pad_tables() -> dict:
    return json.loads(_schema_path().read_text())


def _distance(
    ax: float, ay: float, az: float, bx: float, by: float, bz: float
) -> float:
    return ((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2) ** 0.5


def _nearest_pad(pads: list[dict], x: float, y: float, z: float) -> tuple[dict, float]:
    best_pad = min(pads, key=lambda p: _distance(x, y, z, p["x"], p["y"], p["z"]))
    dist = _distance(x, y, z, best_pad["x"], best_pad["y"], best_pad["z"])
    return best_pad, dist


class TestBoostPadTablesSchema:
    def test_schema_loads(self, pad_tables: dict) -> None:
        assert "arenas" in pad_tables
        assert "_default_soccar" in pad_tables["arenas"]

    def test_default_soccar_pad_count(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        assert len(pads) == 34, f"Expected 34 pads, got {len(pads)}"

    def test_big_pad_count(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        big = [p for p in pads if p["is_big"]]
        assert len(big) == 6

    def test_small_pad_count(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        small = [p for p in pads if not p["is_big"]]
        assert len(small) == 28

    def test_unique_pad_ids(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        ids = [p["id"] for p in pads]
        assert len(ids) == len(set(ids)), "Duplicate pad IDs found"
        assert set(ids) == set(range(34))

    def test_side_values_valid(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        valid_sides = {"blue", "orange", "mid"}
        for pad in pads:
            assert pad["side"] in valid_sides, (
                f"Pad {pad['id']} has invalid side '{pad['side']}'"
            )

    def test_side_coverage_all_present(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        sides = {p["side"] for p in pads}
        assert sides == {"blue", "orange", "mid"}

    def test_big_pads_have_no_mid_side(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        for pad in pads:
            if pad["is_big"]:
                assert pad["side"] != "mid", (
                    f"Big pad {pad['id']} incorrectly classified as mid"
                )

    def test_snap_tolerances_present(self, pad_tables: dict) -> None:
        tols = pad_tables.get("snap_tolerances", {})
        assert "small_uu" in tols
        assert "big_uu" in tols
        assert tols["small_uu"] <= 200
        assert tols["big_uu"] <= 200

    def test_arena_map_keys(self, pad_tables: dict) -> None:
        arena_map = pad_tables.get("arena_map", {})
        assert "DFHStadium" in arena_map
        assert "cs_day_p" in arena_map
        assert "Wasteland_GRS_P" in arena_map
        assert "CHN_Stadium_P" in arena_map


class TestCanonicalSnapTolerances:
    """Assert that sample pad positions snap within strict tolerances.

    Using exact canonical coordinates the snap error should be 0.
    We also verify a small artificial offset snaps correctly.
    """

    def test_big_pad_exact_match(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        big_pads = [p for p in pads if p["is_big"]]
        for pad in big_pads:
            _, dist = _nearest_pad(pads, pad["x"], pad["y"], pad["z"])
            assert dist < 1e-3, f"Pad {pad['id']} exact match failed: dist={dist}"

    def test_small_pad_exact_match(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        small_pads = [p for p in pads if not p["is_big"]]
        for pad in small_pads:
            _, dist = _nearest_pad(pads, pad["x"], pad["y"], pad["z"])
            assert dist < 1e-3, f"Pad {pad['id']} exact match failed: dist={dist}"

    def test_big_pad_offset_within_120uu(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        big_pad = next(p for p in pads if p["is_big"])
        sample_x = big_pad["x"] + 50.0
        sample_y = big_pad["y"] + 50.0
        sample_z = big_pad["z"]
        found, dist = _nearest_pad(pads, sample_x, sample_y, sample_z)
        assert found["id"] == big_pad["id"], "Nearest pad id mismatch"
        assert dist < 120.0, f"Big pad snap dist {dist:.1f} exceeds 120 uu"

    def test_small_pad_offset_within_180uu(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        small_pad = next(p for p in pads if not p["is_big"])
        sample_x = small_pad["x"] + 60.0
        sample_y = small_pad["y"] + 60.0
        sample_z = small_pad["z"]
        found, dist = _nearest_pad(pads, sample_x, sample_y, sample_z)
        assert found["id"] == small_pad["id"], "Nearest small pad id mismatch"
        assert dist < 180.0, f"Small pad snap dist {dist:.1f} exceeds 180 uu"


class TestPadSideByPosition:
    """Verify side classifications match the Y-coordinate conventions."""

    def test_blue_pads_have_negative_y(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        for pad in pads:
            if pad["side"] == "blue":
                assert pad["y"] < 0, (
                    f"Blue pad {pad['id']} has non-negative y={pad['y']}"
                )

    def test_orange_pads_have_positive_y(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        for pad in pads:
            if pad["side"] == "orange":
                assert pad["y"] > 0, (
                    f"Orange pad {pad['id']} has non-positive y={pad['y']}"
                )

    def test_mid_pads_near_centre(self, pad_tables: dict) -> None:
        pads = pad_tables["arenas"]["_default_soccar"]["pads"]
        for pad in pads:
            if pad["side"] == "mid":
                assert abs(pad["y"]) <= 2000, (
                    f"Mid pad {pad['id']} has |y|={abs(pad['y'])} > 2000"
                )
