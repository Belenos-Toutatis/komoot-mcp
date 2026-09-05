"""Pytest fixtures and fakes for routing tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


class FakeMCP:
    """Minimal MCP mock that captures tool registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        def deco(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        if len(args) == 1 and callable(args[0]):
            return deco(args[0])
        return deco


class FakeClient:
    """Minimal KomootClient mock that returns fixtures and captures requests.

    Args:
        route_response: The dict that post_www('/routing/tour', ...) returns.
    """

    def __init__(self, route_response: dict[str, Any] | None = None) -> None:
        self.route_response = route_response or {}
        self.last_request: dict[str, Any] | None = None

    async def post_www(self, path: str, **kwargs: Any) -> Any:
        if path == "/routing/tour":
            return self.route_response
        msg = f"FakeClient.post_www: unexpected path {path!r}"
        raise NotImplementedError(msg)

    async def get(self, path: str, **kwargs: Any) -> Any:
        msg = f"FakeClient.get: unexpected path {path!r}"
        raise NotImplementedError(msg)

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.last_request = {"method": method, "url": url, **kwargs}
        return {"status": "captured", "captured": True}


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON test fixture from tests/fixtures/."""
    path = FIXTURES / name
    with open(path) as f:
        return json.load(f)