"""MCP tools for Komoot highlights (points d'interet), tips, photos et favoris."""

from __future__ import annotations

from typing import Any

from ..client import API_V006, KomootClient, KomootError


def register(mcp, client: KomootClient) -> None:
    @mcp.tool()
    async def get_highlight(
        highlight_id: int,
        include_tips: bool = False,
        include_recommenders: bool = False,
    ) -> dict[str, Any]:
        """Detail d'un highlight Komoot (point d'interet communautaire).

        Args:
            highlight_id: ID du highlight.
            include_tips: ajouter la premiere page de conseils de la communaute.
            include_recommenders: ajouter les utilisateurs qui le recommandent.
        """
        result = await client.get(f"/highlights/{highlight_id}")
        if include_tips:
            result["tips"] = await client.get(f"/highlights/{highlight_id}/tips/", page=0)
        if include_recommenders:
            result["recommenders"] = await client.get(f"/highlights/{highlight_id}/recommenders/")
        return result

    @mcp.tool()
    async def get_highlight_tips(highlight_id: int, page: int = 0) -> dict[str, Any]:
        """Conseils/tips de la communaute pour un highlight.

        Args:
            highlight_id: ID du highlight.
            page: page de resultats (0-indexee).
        """
        return await client.get(f"/highlights/{highlight_id}/tips/", page=page)

    @mcp.tool()
    async def get_highlight_images(highlight_id: int, page: int = 0) -> dict[str, Any]:
        """Photos d'un highlight publiees par la communaute.

        Les URLs sont des gabarits : remplacer {width}, {height}, {crop} (ex: 800, 600, false).

        Args:
            highlight_id: ID du highlight.
            page: page de resultats (0-indexee).
        """
        return await client.get(f"/highlights/{highlight_id}/images/", page=page)

    @mcp.tool()
    async def get_tour_images(tour_id: int, page: int = 0, limit: int = 20) -> dict[str, Any]:
        """Lister les images/photos d'un tour.

        Args:
            tour_id: ID du tour.
            page: page de resultats.
            limit: nombre d'images par page.
        """
        return await client.get(f"/tours/{tour_id}/cover_images/", page=page, limit=limit)

    @mcp.tool()
    async def list_user_highlights(
        username: str | None = None,
        page: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Highlights recommandes (crees ou votes) par un utilisateur.

        Args:
            username: ID utilisateur Komoot ; par defaut l'utilisateur connecte.
            page: page de resultats.
            limit: nombre par page (max 100).
        """
        return await client.get(
            f"/users/{username or client.user_id}/highlights/", page=page, limit=min(limit, 100),
        )

    @mcp.tool()
    async def find_highlights_nearby(
        lat: float,
        lng: float,
        radius_m: int = 5000,
        sport: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Highlights de la communaute autour d'un point (cascades, sommets, cafes, points de vue...).

        Args:
            lat: latitude du centre.
            lng: longitude du centre.
            radius_m: rayon de recherche en metres.
            sport: ne garder que les highlights d'un sport ('hike', 'touringbicycle', 'mtb', ...).
            limit: nombre maximal de resultats (max 100).
        """
        items = await client.get(
            f"{API_V006}/user_highlights/",
            lat=lat, lon=lng, max_distance=radius_m,
            items_range=f"0-{min(max(limit, 1), 100) - 1}", srid=4326,
        )
        items = items if isinstance(items, list) else []
        if sport:
            items = [h for h in items if h.get("sport") == sport]
        return items

    @mcp.tool()
    async def list_bookmarked_highlights(limit: int = 100) -> list[dict[str, Any]]:
        """Highlights mis en favori (enregistres) par l'utilisateur connecte.

        Args:
            limit: nombre maximal de resultats (max 100, limite de Komoot).
        """
        items = await client.get(
            f"{API_V006}/users/{client.user_id}/bookmarked_user_highlights/recent/",
            srid=4326, items_range=f"0-{min(max(limit, 1), 100) - 1}",
            fields="start_point,mid_point,images",
        )
        return items if isinstance(items, list) else []

    @mcp.tool()
    async def bookmark_highlight(highlight_id: int) -> dict[str, Any]:
        """Ajouter un highlight aux favoris (enregistres) de l'utilisateur.

        Args:
            highlight_id: ID du highlight.
        """
        try:
            await client.post(f"{API_V006}/users/{client.user_id}/bookmarked_user_highlights/{highlight_id}")
        except KomootError as exc:
            # Komoot repond 400 "already bookmarked" (409 selon d'autres clients)
            if exc.status != 409 and "already" not in exc.body:
                raise
            return {"highlight_id": highlight_id, "bookmarked": True, "already": True}
        return {"highlight_id": highlight_id, "bookmarked": True}

    @mcp.tool()
    async def unbookmark_highlight(highlight_id: int) -> dict[str, Any]:
        """Retirer un highlight des favoris de l'utilisateur.

        Args:
            highlight_id: ID du highlight.
        """
        try:
            await client.delete(f"{API_V006}/users/{client.user_id}/bookmarked_user_highlights/{highlight_id}")
        except KomootError as exc:
            if exc.status != 404:
                raise
        return {"highlight_id": highlight_id, "bookmarked": False}
