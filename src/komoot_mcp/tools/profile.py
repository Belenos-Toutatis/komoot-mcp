"""MCP tools for Komoot user profile."""

from __future__ import annotations

from typing import Any

from ..client import KomootClient


def register(mcp, client: KomootClient) -> None:
    @mcp.tool()
    async def get_user_profile(username: str | None = None) -> dict[str, Any]:
        """Profil Komoot : complet pour l'utilisateur connecte, public pour un autre utilisateur.

        Args:
            username: ID utilisateur Komoot d'une autre personne ; vide = soi-meme.
        """
        if username and username != client.user_id:
            return await client.get(f"/users/{username}/profile_embedded")
        return await client.get(f"/users/{client.user_id}")
