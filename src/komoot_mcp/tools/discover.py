"""MCP tools for Komoot discovery — Smart Tours, attributs de parcours, collections.

Endpoints verifies en direct (octobre 2026), repris du projet Eric-AI-M/komoot-mcp-server.
"""

from __future__ import annotations

from typing import Any

from ..client import WWW_V007, KomootClient
from .exports import _write


def _summarize(item: dict[str, Any]) -> dict[str, Any]:
    """Version compacte d'un tour / Smart Tour / element de collection."""
    out = {k: item.get(k) for k in ("id", "type", "name", "sport", "status") if item.get(k) is not None}
    if "distance" in item:
        out["distance_km"] = round(item["distance"] / 1000, 1)
    if "duration" in item:
        out["duration_h"] = round(item["duration"] / 3600, 2)
    for k in ("elevation_up", "elevation_down"):
        if k in item:
            out[f"{k}_m"] = round(item[k])
    if isinstance(item.get("difficulty"), dict):
        out["difficulty"] = item["difficulty"].get("grade")
    if item.get("start_point"):
        out["start"] = {k: item["start_point"].get(k) for k in ("lat", "lng")}
    if item.get("smart_tour_type"):
        out["smart_tour_type"] = item["smart_tour_type"]
    surfaces = (item.get("summary") or {}).get("surfaces")
    if surfaces:
        top = sorted((s for s in surfaces if "type" in s), key=lambda s: -s.get("amount", 0))[:4]
        out["surfaces"] = {s["type"]: round(s["amount"], 2) for s in top}
    if item.get("type") in ("tour_planned", "tour_recorded"):
        out["url"] = f"https://www.komoot.com/tour/{item['id']}"
    elif item.get("type") in ("highlight_point", "highlight_segment"):
        out["url"] = f"https://www.komoot.com/highlight/{item['id']}"
    if not out.get("name") and isinstance(item.get("collection"), dict):
        return _summarize(item["collection"])
    return out


def _compact_page(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    items = (result.get("_embedded") or {}).get("items", [])
    return {"page": result.get("page"), "items": [_summarize(i) for i in items]}


def register(mcp, client: KomootClient) -> None:
    @mcp.tool()
    async def find_smart_tours(
        lat: float,
        lng: float,
        sport: str = "hike",
        max_distance_m: int = 20000,
        route_attributes: str | None = None,
        highlight_id: int | None = None,
        page: int = 0,
        compact: bool = True,
    ) -> dict[str, Any]:
        """Suggestions d'itineraires Komoot (Smart Tours) autour d'un point.

        Args:
            lat: latitude de depart.
            lng: longitude de depart.
            sport: 'hike', 'touringbicycle', 'mtb', 'racebicycle', 'jogging', ...
            max_distance_m: rayon de recherche autour du point, en metres.
            route_attributes: attributs separes par virgule (ex: 'forests,lakes_rivers'), combines
                              en ET ; voir list_route_attributes pour les valeurs possibles.
            highlight_id: ne garder que les tours passant par ce highlight.
            page: page de resultats.
            compact: resume par tour (id, nom, distance, denivele, difficulte) ; False = JSON brut
                     tres volumineux (~8 000 caracteres par tour).
        """
        result = await client.get(
            f"{WWW_V007}/discover_tours/from_location/",
            lat=lat, lng=lng, sport=sport, max_distance=max_distance_m,
            route_attributes=route_attributes, highlight_id=highlight_id, page=page,
        )
        return _compact_page(result) if compact else result

    @mcp.tool()
    async def list_route_attributes(
        lat: float,
        lng: float,
        sport: str = "hike",
        max_distance_m: int = 20000,
    ) -> dict[str, Any]:
        """Attributs de parcours disponibles autour d'un point (cascades, lacs, refuges,
        sommets, adapte aux chiens/familles...), a passer a find_smart_tours.

        Args:
            lat: latitude.
            lng: longitude.
            sport: type de sport.
            max_distance_m: rayon en metres.
        """
        return await client.get(
            f"{WWW_V007}/discover_tours/route_attributes/",
            lat=lat, lng=lng, sport=sport, max_distance=max_distance_m,
        )

    @mcp.tool()
    async def get_smart_tour(smart_tour_id: int) -> dict[str, Any]:
        """Detail d'un Smart Tour (distance, denivele, difficulte, points de passage).

        Args:
            smart_tour_id: ID renvoye par find_smart_tours.
        """
        return await client.get(f"/discover_tours/{smart_tour_id}")

    @mcp.tool()
    async def download_smart_tour_gpx(smart_tour_id: int, save_path: str | None = None) -> str:
        """Telecharger le GPX d'un Smart Tour.

        Args:
            smart_tour_id: ID renvoye par find_smart_tours.
            save_path: fichier ou dossier d'enregistrement ; sinon le XML est renvoye.
        """
        data = await client.get(f"/smart_tours/{smart_tour_id}.gpx", raw=True)
        if save_path:
            path = _write(save_path, f"smart_{smart_tour_id}.gpx", data)
            return f"GPX enregistre : {path} ({len(data)} octets)"
        return data.decode("utf-8")

    @mcp.tool()
    async def discover_near(lat: float, lng: float, page: int = 0,
                            compact: bool = True) -> dict[str, Any]:
        """Contenus editoriaux Komoot autour d'un point (collections, selections de tours).

        Args:
            lat: latitude.
            lng: longitude.
            page: page de resultats.
            compact: resume par element ; False = JSON brut.
        """
        result = await client.get(
            f"/discover/{lat},{lng}/elements/", page=page, _embedded="main_tour,summary",
        )
        return _compact_page(result) if compact else result

    @mcp.tool()
    async def get_collection(collection_id: int) -> dict[str, Any]:
        """Metadonnees d'une collection Komoot (titre, intro, createur, sport).

        Args:
            collection_id: ID de la collection (ex: depuis discover_near ou une URL /collection/...).
        """
        return await client.get(f"/collections/{collection_id}")

    @mcp.tool()
    async def get_collection_tours(collection_id: int, page: int = 0,
                                   compact: bool = True) -> dict[str, Any]:
        """Tours et highlights contenus dans une collection.

        Args:
            collection_id: ID de la collection.
            page: page de resultats.
            compact: resume par element ; False = JSON brut (tres volumineux).
        """
        result = await client.get(f"/collections/{collection_id}/compilation/", page=page)
        return _compact_page(result) if compact else result
