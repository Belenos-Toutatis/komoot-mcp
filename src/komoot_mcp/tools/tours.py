"""MCP tools for Komoot tours — list, get, update, delete."""

from __future__ import annotations

from typing import Any

from ..client import KomootClient

# Embeds renvoyes par get_tour_full (meme requete que le front web Komoot)
_FULL_EMBEDS = "coordinates,way_types,surfaces,directions,participants,timeline,cover_images"


def register(mcp, client: KomootClient) -> None:
    @mcp.tool()
    async def list_tours(
        tour_type: str | None = None,
        sport_types: str | None = None,
        status: str | None = None,
        sort_field: str = "date",
        sort_direction: str = "desc",
        name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 0,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Lister tes tours Komoot (planifies et enregistres).

        Args:
            tour_type: 'tour_planned', 'tour_recorded', ou None pour tous.
            sport_types: types de sport separes par virgule (ex: 'hike,touringbicycle,mtb,racebicycle,jogging').
            status: 'public', 'friends', 'private', ou None pour tous
                    (filtre applique localement : Komoot l'ignore pour ses propres tours).
            sort_field: champ de tri ('date', 'name', 'distance', 'duration', 'elevation').
            sort_direction: 'asc' ou 'desc'.
            name: filtrer par nom (recherche partielle).
            start_date: date ISO 8601 minimale (ex: '2026-01-01' ou '2026-01-01T00:00:00Z').
            end_date: date ISO 8601 maximale.
            page: pagination (0-indexee).
            limit: nb max (defaut 30, max 100).
        """
        result = await client.get(
            f"/users/{client.user_id}/tours/",
            type=tour_type,
            sport_types=sport_types,
            sort_field=sort_field,
            sort_direction=sort_direction,
            name=name,
            start_date=_iso(start_date),
            end_date=_iso(end_date, end_of_day=True),
            page=page,
            limit=min(limit, 100),
        )
        if status and isinstance(result, dict):
            tours = result.get("_embedded", {}).get("tours", [])
            result["_embedded"]["tours"] = [t for t in tours if t.get("status") == status]
        return result

    @mcp.tool()
    async def get_tour(tour_id: int, share_token: str | None = None) -> dict[str, Any]:
        """Detail d'un tour (distance, denivele, duree, sport, difficulte, resume surfaces/voies).

        Args:
            tour_id: ID du tour Komoot.
            share_token: jeton de partage, pour un tour prive d'un autre utilisateur.
        """
        return await client.get(f"/tours/{tour_id}", share_token=share_token)

    @mcp.tool()
    async def get_tour_full(tour_id: int, include_coordinates: bool = False) -> dict[str, Any]:
        """Tour complet en UN appel : metadonnees + surfaces, types de voie, directions,
        participants, timeline (highlights traverses avec tips) et photos.

        Remplace la serie get_tour + get_tour_surfaces + get_tour_way_types + get_tour_directions
        + get_tour_images.

        Args:
            tour_id: ID du tour.
            include_coordinates: inclure la trace complete (volumineux ; False par defaut).
        """
        embeds = _FULL_EMBEDS if include_coordinates else _FULL_EMBEDS.replace("coordinates,", "")
        return await client.get(
            f"/tours/{tour_id}",
            _embedded=embeds,
            directions="v2",
            fields="timeline",
            format="coordinate_array",
            timeline_highlights_fields="tips,recommenders",
        )

    @mcp.tool()
    async def update_tour(
        tour_id: int,
        name: str | None = None,
        sport: str | None = None,
        status: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Modifier les metadonnees d'un tour (seuls les champs fournis sont envoyes).

        Args:
            tour_id: ID du tour.
            name: nouveau nom.
            sport: type de sport ('hike', 'touringbicycle', 'mtb', 'racebicycle',
                   'jogging', 'mountaineering', 'running', 'e_touringbicycle',
                   'e_mtb', 'mtb_easy', 'mtb_advanced', 'e_racebicycle', 'nordic_walking',
                   'skitour', 'snowshoe').
            status: 'public', 'friends' ou 'private'.
            description: texte de description du tour.
        """
        if all(v is None for v in (name, sport, status, description)):
            raise ValueError("Rien a modifier : fournir au moins un champ.")
        return await client.patch(
            f"/tours/{tour_id}",
            name=name,
            sport=sport,
            status=status,
            description=description,
        )

    @mcp.tool()
    async def delete_tour(tour_id: int) -> dict[str, str]:
        """Supprimer un tour (definitif).

        Args:
            tour_id: ID du tour a supprimer.
        """
        await client.delete(f"/tours/{tour_id}")
        return {"deleted": str(tour_id)}


def _iso(value: str | None, end_of_day: bool = False) -> str | None:
    """Complete une date 'AAAA-MM-JJ' en timestamp ISO 8601 UTC attendu par Komoot."""
    if value is None or "T" in value:
        return value
    return f"{value}T23:59:59.999Z" if end_of_day else f"{value}T00:00:00.000Z"
