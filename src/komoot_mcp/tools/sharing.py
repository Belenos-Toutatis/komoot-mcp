"""MCP tools for sharing Komoot tours (liens de partage)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..client import API_BASE, KomootClient


def register(mcp, client: KomootClient) -> None:
    @mcp.tool()
    async def create_share_link(tour_id: int) -> dict[str, Any]:
        """Creer un lien de partage pour un tour (visible sans compte, meme si le tour est prive).

        Args:
            tour_id: ID du tour.
        """
        result = await client.post(
            f"/tours/{tour_id}/share_token", json_body={}, params={"format": "v2", "hl": "fr"},
        )
        token = result.get("token") if isinstance(result, dict) else None
        if not token:
            return {"raw": result}
        return {
            "tour_id": tour_id,
            "share_token": token,
            "share_url": f"https://www.komoot.com/tour/{tour_id}?share_token={token}",
        }

    @mcp.tool()
    async def revoke_share_link(tour_id: int) -> dict[str, Any]:
        """Revoquer le lien de partage d'un tour.

        Args:
            tour_id: ID du tour.
        """
        await client.delete(f"/tours/{tour_id}/share_token")
        return {"tour_id": tour_id, "share_link": "revoked"}

    @mcp.tool()
    async def get_shared_tour(share_url: str) -> dict[str, Any]:
        """Lire un tour a partir d'une URL Komoot (lien de partage ou URL /tour/<id>).

        Args:
            share_url: ex. 'https://www.komoot.com/tour/123456?share_token=abc...'.
        """
        match = re.search(r"/tour/(\d+)", share_url)
        if not match:
            raise ValueError(f"Aucun ID de tour dans l'URL : {share_url}")
        tour_id = match.group(1)
        token = parse_qs(urlparse(share_url).query).get("share_token", [None])[0]
        if token:
            tour = await client.get_public(f"{API_BASE}/tours/{tour_id}", share_token=token)
        else:
            tour = await client.get(f"/tours/{tour_id}")
        return {"tour_id": int(tour_id), "share_token": token, "tour": tour}
