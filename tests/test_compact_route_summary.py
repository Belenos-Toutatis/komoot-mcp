"""Tests for _compact_route_summary.

Verifies distance, elevation, duration, difficulty (T/C),
way_types, surfaces, singletrail, segments, matched_coordinates,
and absence of the full coordinate list.
"""

from __future__ import annotations

from typing import Any

from komoot_mcp.tools.routing import _compact_route_summary


def _make_raw(**overrides: Any) -> dict[str, Any]:
    """Build a minimal synthetic plan_route response."""
    raw: dict[str, Any] = {
        "distance": 33400.0,
        "elevation_up": 976.0,
        "elevation_down": 976.0,
        "duration": 10800,
        "difficulty": {
            "grade": "DIFFICULT",
            "explanation_technical": "f#T2",
            "explanation_fitness": "c#C3",
        },
        "summary": {
            "way_types": [
                {"type": "wt#highway", "amount": 0.143},
                {"type": "wt#trail", "amount": 0.094},
            ],
            "surfaces": [
                {"type": "sm#asphalt", "amount": 0.063},
                {"type": "sm#gravel", "amount": 0.530},
            ],
        },
        "_embedded": {
            "way_types": {
                "items": [
                    {"from": 0, "to": 2, "element": "wt#trail_d1"},
                ],
            },
            "coordinates": {
                "items": [
                    {"lat": 0.0, "lng": 0.0, "alt": 0.0},
                    {"lat": 0.0, "lng": 0.5, "alt": 0.0},
                    {"lat": 0.0, "lng": 1.0, "alt": 0.0},
                ],
            },
        },
        "segments": [
            {"type": "Routed"},
            {"type": "Routed"},
            {"type": "Manual"},
        ],
        "tour_information": [
            {"type": "STEEP_UPHILL", "segments": [1, 2]},
        ],
    }
    raw.update(overrides)
    return raw


# ── Distance & Elevation ───────────────────────────────────────────────

def test_distance_km() -> None:
    result = _compact_route_summary(_make_raw())
    assert result["distance_km"] == 33.4
    assert result["distance_m"] == 33400.0


def test_elevation() -> None:
    result = _compact_route_summary(_make_raw())
    assert result["elevation_up_m"] == 976.0
    assert result["elevation_down_m"] == 976.0


# ── Duration ───────────────────────────────────────────────────────────

def test_duration_hours_and_minutes() -> None:
    """10800 s = 3h 0m."""
    result = _compact_route_summary(_make_raw())
    assert result["duration_seconds"] == 10800
    assert result["duration"] == "3h 0m"


def test_duration_minutes_only() -> None:
    """600 s = 10m (no h)."""
    result = _compact_route_summary(_make_raw(duration=600))
    assert result["duration"] == "10m"


def test_duration_zero() -> None:
    result = _compact_route_summary(_make_raw(duration=0))
    assert result["duration"] == "0m"


# ── Difficulty (T/C) ───────────────────────────────────────────────────

def test_difficulty_grade() -> None:
    result = _compact_route_summary(_make_raw())
    assert result["difficulty"] == "DIFFICULT"


def test_technical_difficulty() -> None:
    result = _compact_route_summary(_make_raw())
    assert result["technical_difficulty"] == "T2"


def test_fitness_difficulty() -> None:
    result = _compact_route_summary(_make_raw())
    assert result["fitness_difficulty"] == "C3"


def test_difficulty_edge_cases() -> None:
    """No difficulty dict → no difficulty keys."""
    result = _compact_route_summary(_make_raw(difficulty={}))
    assert "difficulty" not in result
    assert "technical_difficulty" not in result
    assert "fitness_difficulty" not in result


# ── Way types ──────────────────────────────────────────────────────────

def test_way_types_structure() -> None:
    result = _compact_route_summary(_make_raw())
    wts = result["way_types"]
    assert "highway" in wts
    assert "trail" in wts
    # 0.143 * 100 = 14.3
    assert wts["highway"]["percentage"] == 14.3
    # 0.143 * 33.4 = 4.7762 → round(2) = 4.78
    assert wts["highway"]["distance_km"] == 4.78


# ── Surfaces ───────────────────────────────────────────────────────────

def test_surfaces_structure() -> None:
    result = _compact_route_summary(_make_raw())
    sfs = result["surfaces"]
    assert "asphalt" in sfs
    assert "gravel" in sfs
    assert sfs["asphalt"]["percentage"] == 6.3


# ── Singletrail ────────────────────────────────────────────────────────

def test_singletrail_present() -> None:
    result = _compact_route_summary(_make_raw())
    st = result["singletrail"]
    assert "trail_d1" in st
    assert st["trail_d1"]["distance_km"] > 0
    assert "singletrail_total_km" in st


def test_singletrail_no_trail() -> None:
    """No trail_d* items → available=False."""
    raw = _make_raw()
    raw["_embedded"]["way_types"]["items"] = [
        {"from": 0, "to": 2, "element": "wt#highway"},
    ]
    result = _compact_route_summary(raw)
    assert result["singletrail"] == {"available": False}


# ── Segments ───────────────────────────────────────────────────────────

def test_segments() -> None:
    result = _compact_route_summary(_make_raw())
    assert result["segments"] == {"routed": 2, "manual": 1}


def test_segments_all_routed() -> None:
    raw = _make_raw(segments=[{"type": "Routed"}, {"type": "Routed"}])
    result = _compact_route_summary(raw)
    assert result["segments"] == {"routed": 2, "manual": 0}


# ── Tour information ───────────────────────────────────────────────────

def test_tour_information() -> None:
    result = _compact_route_summary(_make_raw())
    assert "tour_information" in result
    assert result["tour_information"] == [{"type": "STEEP_UPHILL", "segments": 2}]


# ── Matched coordinates (count, NOT list) ──────────────────────────────

def test_matched_coordinates_count() -> None:
    result = _compact_route_summary(_make_raw())
    assert result["matched_coordinates"] == 3
    assert isinstance(result["matched_coordinates"], int)


def test_no_full_coordinate_list() -> None:
    """Compact output MUST NOT contain 'path' or 'coordinates' as full lists."""
    result = _compact_route_summary(_make_raw())
    assert "path" not in result
    # 'coordinates' key should not be a list; it's either absent or a count
    if "coordinates" in result:
        assert isinstance(result["coordinates"], int), "coordinates must be a count, not a list"


# ── Edge cases ─────────────────────────────────────────────────────────

def test_missing_keys() -> None:
    """Empty raw response produces no crash, has empty defaults."""
    result = _compact_route_summary({})
    # No distance/elevation/duration/difficulty keys
    assert "distance_km" not in result
    # Empty defaults for iterable fields
    assert result["way_types"] == {}
    assert result["surfaces"] == {}
    assert result["segments"] == {"routed": 0, "manual": 0}
    assert result["singletrail"] == {"available": False}


def test_partial_data() -> None:
    """Only distance present → only distance fields."""
    result = _compact_route_summary({"distance": 10000})
    assert result["distance_km"] == 10.0
    assert "elevation_up_m" not in result
    assert "duration" not in result