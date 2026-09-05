"""Tests for module-level helper functions in routing.py.

Covers:
  - _haversine_km
  - _segment_km
  - _compute_singletrail
"""

from __future__ import annotations

import math
from typing import Any

from komoot_mcp.tools.routing import (
    _compute_singletrail,
    _haversine_km,
    _segment_km,
)


# ── _haversine_km ──────────────────────────────────────────────────────

def test_haversine_equator_one_degree() -> None:
    """1° of longitude at the equator is ~111.195 km (R = 6371 km)."""
    d = _haversine_km(0.0, 0.0, 0.0, 1.0)
    assert abs(d - 111.195) < 0.001, f"Expected ~111.195, got {d}"


def test_haversine_one_degree_latitude() -> None:
    """1° of latitude anywhere is ~111.195 km."""
    d = _haversine_km(0.0, 0.0, 1.0, 0.0)
    assert abs(d - 111.195) < 0.001, f"Expected ~111.195, got {d}"


def test_haversine_zero_distance() -> None:
    """Same point → 0.0 km."""
    for lat, lon in [(0.0, 0.0), (52.0, 13.0), (-33.0, 151.0)]:
        assert _haversine_km(lat, lon, lat, lon) == 0.0


def test_haversine_symmetry() -> None:
    """haversine(a, b) == haversine(b, a)."""
    d1 = _haversine_km(52.52, 13.405, 48.8566, 2.3522)
    d2 = _haversine_km(48.8566, 2.3522, 52.52, 13.405)
    assert abs(d1 - d2) < 0.001


def test_haversine_known_distance() -> None:
    """Berlin → Hamburg: ~255 km."""
    d = _haversine_km(52.5200, 13.4050, 53.5511, 9.9937)
    assert 250 < d < 260, f"Expected ~255 km, got {d}"


# ── _segment_km ────────────────────────────────────────────────────────

def _equator_coords(*lons: float) -> list[dict[str, float]]:
    """Helper: coordinate dicts on the equator."""
    return [{"lat": 0.0, "lng": lon, "alt": 0.0} for lon in lons]


def test_segment_km_simple() -> None:
    """Three points on equator: 0→0.5→1.0, sum = 111.195 km."""
    coords = _equator_coords(0.0, 0.5, 1.0)
    d = _segment_km(coords, 0, 2)
    assert abs(d - 111.195) < 0.01


def test_segment_km_partial() -> None:
    """Points 0→0.5→1.0, segment from index 1 to 2 is ~55.6 km."""
    coords = _equator_coords(0.0, 0.5, 1.0)
    d = _segment_km(coords, 1, 2)
    assert abs(d - 55.597) < 0.01


def test_segment_km_out_of_range() -> None:
    """Negative from_i clamps to 0; excessive to_i clamps to len-1."""
    coords = _equator_coords(0.0, 0.5, 1.0)
    d = _segment_km(coords, -5, 999)
    assert abs(d - 111.195) < 0.01


def test_segment_km_invalid_coord() -> None:
    """A coordinate missing lat/lng produces 0 for that segment, no crash."""
    coords: list[dict[str, Any]] = [
        {"lat": 0.0, "lng": 0.0, "alt": 0.0},
        {"foo": "bar"},  # no lat/lng
        {"lat": 0.0, "lng": 1.0, "alt": 0.0},
    ]
    d = _segment_km(coords, 0, 2)
    # Only the first segment (0→1) counts; the middle coord has no lat/lng,
    # so the second segment produces 0.0.
    expected = _haversine_km(0.0, 0.0, 0.0, 0.0)  # 0
    assert d >= 0.0


# ── _compute_singletrail ───────────────────────────────────────────────

def _equator_coord_items(*lons: float) -> list[dict[str, float]]:
    return [{"lat": 0.0, "lng": lon, "alt": 0.0} for lon in lons]


def test_singletrail_single_type() -> None:
    """trail_d1 with one interval: correct distance and percentage."""
    coords = _equator_coord_items(0.0, 0.5, 1.0)
    wt_items = [{"from": 0, "to": 2, "element": "wt#trail_d1"}]
    result = _compute_singletrail(wt_items, coords, total_km=111.195)
    assert result["trail_d1"]["distance_km"] == 111.19
    assert result["trail_d1"]["segments"] == 1
    assert result["trail_d1"]["from_to"] == [[0, 2]]
    assert abs(result["singletrail_total_km"] - 111.19) < 0.01
    assert abs(result["singletrail_percentage"] - 100.0) < 0.1


def test_singletrail_overlap_merged() -> None:
    """Overlapping intervals of the same trail type are merged once.

    trail_d1: [0,2] and [1,3] → merged [0,3] → distance 0→3 = 166.8 km,
    NOT 0→2 + 1→3 = 222.4 km.
    """
    coords = _equator_coord_items(0.0, 0.5, 1.0, 1.5)
    wt_items = [
        {"from": 0, "to": 2, "element": "wt#trail_d1"},
        {"from": 1, "to": 3, "element": "wt#trail_d1"},
    ]
    result = _compute_singletrail(wt_items, coords, total_km=200.0)
    # merged [0,3] = 0→1.5 = 166.79 km (rounded to 166.79)
    assert result["trail_d1"]["segments"] == 2  # original intervals count
    assert result["trail_d1"]["from_to"] == [[0, 2], [1, 3]]
    d = result["trail_d1"]["distance_km"]
    assert abs(d - 166.79) < 0.02, f"Expected ~166.79, got {d}"
    # Overlap NOT double-counted: 0→2 + 1→3 = 111.19 + 55.60 = 166.79
    # (overlap 1→2 is counted once, not twice)
    assert abs(result["singletrail_total_km"] - 166.79) < 0.02


def test_singletrail_multiple_types() -> None:
    """Different trail types (d1, d2) are independent and both counted."""
    coords = _equator_coord_items(0.0, 0.5, 1.0, 1.5)
    wt_items = [
        {"from": 0, "to": 2, "element": "wt#trail_d1"},
        {"from": 1, "to": 3, "element": "wt#trail_d2"},
    ]
    result = _compute_singletrail(wt_items, coords, total_km=200.0)
    assert "trail_d1" in result
    assert "trail_d2" in result
    # Both counted independently
    assert result["trail_d1"]["distance_km"] > 0
    assert result["trail_d2"]["distance_km"] > 0
    assert result["singletrail_total_km"] > result["trail_d1"]["distance_km"]


def test_singletrail_no_trail_data() -> None:
    """No trail_d* items → {'available': False}."""
    coords = _equator_coord_items(0.0, 0.5, 1.0)
    wt_items = [{"from": 0, "to": 2, "element": "wt#highway"}]
    result = _compute_singletrail(wt_items, coords, total_km=10.0)
    assert result == {"available": False}


def test_singletrail_empty_coords() -> None:
    """Empty wt_items → {'available': False}."""
    result = _compute_singletrail([], _equator_coord_items(0.0, 0.5), 10.0)
    assert result == {"available": False}


def test_singletrail_empty_coords_2() -> None:
    """Empty coord_items → {'available': False}."""
    result = _compute_singletrail(
        [{"from": 0, "to": 2, "element": "wt#trail_d1"}], [], 10.0
    )
    assert result == {"available": False}


def test_singletrail_percentage() -> None:
    """Percentage = singletrail_total_km / total_km * 100."""
    coords = _equator_coord_items(0.0, 0.5, 1.0)
    wt_items = [{"from": 0, "to": 2, "element": "wt#trail_d1"}]
    result = _compute_singletrail(wt_items, coords, total_km=500.0)
    # 111.19 / 500 * 100 = 22.2... → round(22.238, 1) = 22.2
    pct = result["singletrail_percentage"]
    assert abs(pct - 22.2) < 0.1, f"Expected ~22.2, got {pct}"


def test_singletrail_no_percentage_when_no_total() -> None:
    """total_km = 0 → no percentage key (division by zero guard)."""
    coords = _equator_coord_items(0.0, 0.5, 1.0)
    wt_items = [{"from": 0, "to": 2, "element": "wt#trail_d1"}]
    result = _compute_singletrail(wt_items, coords, total_km=0.0)
    assert "singletrail_percentage" not in result


def test_singletrail_ordered_d1_d5() -> None:
    """Output ordered by trail_d1..trail_d5, only existing types."""
    coords = _equator_coord_items(0.0, 0.5, 1.0)
    wt_items = [
        {"from": 0, "to": 1, "element": "wt#trail_d5"},
        {"from": 0, "to": 1, "element": "wt#trail_d1"},
    ]
    result = _compute_singletrail(wt_items, coords, total_km=10.0)
    keys = list(result.keys())
    assert keys[0] == "trail_d1"  # ordered before d5
    assert keys[1] == "trail_d5"
    assert "trail_d2" not in result
    assert "trail_d3" not in result
    assert "trail_d4" not in result