"""Backward compatibility tests for plan_route (compact=False/True) and
the create_planned_tour payload preparation.

Strategy: drive the real closures (plan_route, create_planned_tour) through
register() with a FakeMCP + FakeClient that returns a captured real
compact=False plan_route response from tests/fixtures/. No network calls,
no writes to Komoot.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from komoot_mcp.tools import routing

from conftest import FakeClient, FakeMCP, load_fixture

COORDS = [[47.557, 10.0206], [47.545, 10.105], [47.557, 10.0206]]


@pytest.fixture
def registered() -> tuple[FakeMCP, FakeClient]:
    mcp = FakeMCP()
    # Real captured compact=False response (Oberstaufen MTB route)
    client = FakeClient(route_response=load_fixture("plan_route_full.json"))
    routing.register(mcp, client)
    return mcp, client


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ── compact=False: full response preserved ─────────────────────────────

def test_plan_route_compact_false_full_response(registered: tuple[FakeMCP, FakeClient]) -> None:
    mcp, _client = registered
    plan_route = mcp.tools["plan_route"]
    result = _run(plan_route(COORDS, sport="mtb", compact=False))

    # top-level structure
    assert "path" in result
    assert "segments" in result
    assert "_embedded" in result
    # coordinates
    assert "_embedded" in result
    coords = result["_embedded"]["coordinates"]["items"]
    assert isinstance(coords, list) and len(coords) > 0
    # way_types / surfaces / directions
    for key in ("way_types", "surfaces", "directions"):
        assert key in result["_embedded"], f"missing _embedded.{key}"
    assert len(result["_embedded"]["way_types"]["items"]) > 0
    assert len(result["_embedded"]["surfaces"]["items"]) > 0
    assert len(result["_embedded"]["directions"]["items"]) > 0


def test_plan_route_compact_false_not_summary(registered: tuple[FakeMCP, FakeClient]) -> None:
    """compact=False must NOT return the compact summary."""
    mcp, _client = registered
    plan_route = mcp.tools["plan_route"]
    result = _run(plan_route(COORDS, sport="mtb", compact=False))
    assert "singletrail" not in result
    assert "matched_coordinates" not in result


# ── compact=True: compact summary, no coordinate list ──────────────────

def test_plan_route_compact_true_summary(registered: tuple[FakeMCP, FakeClient]) -> None:
    mcp, _client = registered
    plan_route = mcp.tools["plan_route"]
    result = _run(plan_route(COORDS, sport="mtb", compact=True))

    # core fields
    assert "distance_km" in result
    assert "elevation_up_m" in result
    assert "elevation_down_m" in result
    assert "duration" in result
    assert "difficulty" in result
    assert "way_types" in result
    assert "surfaces" in result
    assert "singletrail" in result
    assert "segments" in result
    assert "matched_coordinates" in result

    # T/C
    assert result["technical_difficulty"].startswith("T")
    assert result["fitness_difficulty"].startswith("C")

    # matched_coordinates is an int count
    assert isinstance(result["matched_coordinates"], int)
    assert result["matched_coordinates"] == 513


def test_plan_route_compact_true_no_coordinate_list(registered: tuple[FakeMCP, FakeClient]) -> None:
    """Compact output must NOT contain a full coordinate/path list."""
    mcp, _client = registered
    plan_route = mcp.tools["plan_route"]
    result = _run(plan_route(COORDS, sport="mtb", compact=True))

    assert "path" not in result
    assert "coordinates" not in result
    assert "_embedded" not in result
    # segments is a summary dict, not the geometry list
    assert isinstance(result["segments"], dict)
    assert set(result["segments"].keys()) == {"routed", "manual"}


def test_plan_route_default_is_false(registered: tuple[FakeMCP, FakeClient]) -> None:
    """Default (no compact arg) must be the full response."""
    mcp, _client = registered
    plan_route = mcp.tools["plan_route"]
    result = _run(plan_route(COORDS, sport="mtb"))
    assert "path" in result and "_embedded" in result
    assert "singletrail" not in result


# ── create_planned_tour payload (NO write to Komoot) ───────────────────

def test_create_planned_tour_payload_with_full_response(registered: tuple[FakeMCP, FakeClient]) -> None:
    """Payload built from a compact=False response must keep path, segments,
    sport, date and must NOT contain _links / uri."""
    mcp, client = registered
    create_tour = mcp.tools["create_planned_tour"]
    full_response = load_fixture("plan_route_full.json")

    result = _run(create_tour(full_response, name="Test Tour", sport="mtb"))
    assert result.get("captured") is True, "should have been captured, not written"

    payload = client.last_request["json_body"]
    assert "path" in payload
    assert "segments" in payload
    assert payload["sport"] == "mtb"
    assert "date" in payload  # preserved from the route response
    assert "_links" not in payload
    assert "uri" not in payload


def test_create_planned_tour_payload_name(registered: tuple[FakeMCP, FakeClient]) -> None:
    mcp, client = registered
    create_tour = mcp.tools["create_planned_tour"]
    full_response = load_fixture("plan_route_full.json")

    _run(create_tour(full_response, name="Meine Tour", sport="hike"))
    payload = client.last_request["json_body"]
    assert payload["name"] == "Meine Tour"
    assert payload["sport"] == "hike"


def test_create_planned_tour_payload_no_mutation(registered: tuple[FakeMCP, FakeClient]) -> None:
    """The original route_data must not be mutated."""
    mcp, client = registered
    create_tour = mcp.tools["create_planned_tour"]
    full_response = load_fixture("plan_route_full.json")
    original_keys = set(full_response.keys())

    _run(create_tour(full_response, name="X", sport="mtb"))
    assert set(full_response.keys()) == original_keys
    assert "_links" not in full_response or "_links" in original_keys
    assert full_response["sport"] == full_response.get("sport")