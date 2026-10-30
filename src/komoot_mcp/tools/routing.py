"""MCP tools for Komoot route planning, import and geocoding.

Le routage passe par www.komoot.com/api (pas api.komoot.de).
Format du payload aligne sur kompy 0.2 (plan_tour) : 'path' de waypoints + un segment
'Routed' par troncon. La sauvegarde se fait par POST /v007/tours/ avec type=tour_planned.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..client import PHOTON_BASE, WWW_V007, KomootClient

_EMBEDS = "coordinates,way_types,surfaces,directions"


def register(mcp, client: KomootClient) -> None:
    async def _route(coordinates: list[list[float]], sport: str, constitution: int,
                     roundtrip: bool) -> dict[str, Any]:
        points = [list(c) for c in coordinates]
        if roundtrip and points and points[0] != points[-1]:
            points.append(points[0])
        if len(points) < 2:
            raise ValueError("Il faut au moins 2 points distincts.")
        if not 1 <= constitution <= 5:
            raise ValueError("constitution doit etre entre 1 et 5.")
        return await client.post_www(
            "/routing/tour",
            json_body={
                "sport": sport,
                "constitution": constitution,
                "path": [{"location": {"lat": p[0], "lng": p[1]}} for p in points],
                "segments": [{"type": "Routed", "geometry": []} for _ in points[1:]],
            },
            params={"sport": sport, "_embedded": _EMBEDS},
        )

    async def _save(route: dict[str, Any], name: str, sport: str | None,
                    status: str) -> dict[str, Any]:
        body = {k: v for k, v in route.items() if k != "result_status"}
        body.update({
            "type": "tour_planned",
            "name": name,
            "status": status,
            "date": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "custom_tags": [],
        })
        if sport:
            body["sport"] = sport
        saved = await client.post("/tours/", json_body=body)
        if isinstance(saved, dict) and "id" in saved:
            return {
                "id": saved["id"],
                "name": saved.get("name"),
                "sport": saved.get("sport"),
                "distance_m": saved.get("distance"),
                "duration_s": saved.get("duration"),
                "elevation_up_m": saved.get("elevation_up"),
                "status": saved.get("status"),
                "url": f"https://www.komoot.com/tour/{saved['id']}",
            }
        return {"raw": str(saved)[:500]}

    @mcp.tool()
    async def import_gpx_route(
        gpx_content: str,
        sport: str = "hike",
    ) -> dict[str, Any]:
        """Importer un fichier GPX et le matcher sur le reseau routier Komoot.

        Etape 1/2 pour creer un tour planifie a partir d'un GPX externe.
        Utiliser ensuite create_planned_tour() avec le resultat.

        Args:
            gpx_content: contenu GPX (texte XML).
            sport: type de sport pour le matching.
        """
        # Etape 1 : upload du fichier
        import_result = await client.post_www(
            "/routing/import/files/",
            data=gpx_content.encode("utf-8"),
            headers={"Content-Type": "application/gpx+xml"},
            params={"data_type": "gpx"},
        )
        if not isinstance(import_result, dict):
            return {"raw": str(import_result)}

        # Etape 2 : route matching
        matched = await client.post_www(
            "/routing/import/tour",
            json_body=import_result,
            params={"sport": sport, "_embedded": _EMBEDS},
        )
        return matched

    @mcp.tool()
    async def plan_route(
        coordinates: list[list[float]],
        sport: str = "hike",
        constitution: int = 3,
        roundtrip: bool = False,
    ) -> dict[str, Any]:
        """Calculer un itineraire avec le planificateur Komoot (sans le sauvegarder).

        Pour sauvegarder directement, preferer plan_and_save_tour (evite de faire transiter
        la trace complete dans la conversation).

        Args:
            coordinates: liste de [lat, lng] des points de passage, dans l'ordre
                         (ex: [[48.5734, 7.7521], [48.5801, 7.7612]]).
            sport: 'hike', 'touringbicycle', 'mtb', 'racebicycle', 'jogging', 'mountaineering', ...
            constitution: niveau de forme 1 (faible) a 5 (excellent), pour l'estimation de duree.
            roundtrip: ajouter le point de depart a la fin (boucle).
        """
        return await _route(coordinates, sport, constitution, roundtrip)

    @mcp.tool()
    async def plan_and_save_tour(
        coordinates: list[list[float]],
        name: str,
        sport: str = "hike",
        constitution: int = 3,
        roundtrip: bool = False,
        status: str = "private",
    ) -> dict[str, Any]:
        """Planifier un itineraire et l'enregistrer comme tour planifie Komoot, en un seul appel.

        Le tour apparait ensuite dans l'app Komoot (onglet Planifies) et peut etre envoye au GPS.

        Args:
            coordinates: liste de [lat, lng] des points de passage, dans l'ordre.
            name: nom du tour.
            sport: type de sport du routage.
            constitution: niveau de forme 1 a 5.
            roundtrip: revenir au point de depart.
            status: 'private', 'friends' ou 'public'.

        Returns:
            id, distance, duree, denivele et URL du tour cree.
        """
        route = await _route(coordinates, sport, constitution, roundtrip)
        return await _save(route, name, sport, status)

    @mcp.tool()
    async def create_planned_tour(
        route_data: dict[str, Any],
        name: str = "Tour planifie",
        sport: str | None = None,
        status: str = "private",
    ) -> dict[str, Any]:
        """Enregistrer comme tour planifie le resultat de plan_route() ou import_gpx_route().

        Args:
            route_data: resultat JSON de plan_route() ou import_gpx_route().
            name: nom du tour planifie.
            sport: type de sport (par defaut celui du routage).
            status: 'private', 'friends' ou 'public'.
        """
        return await _save(route_data, name, sport, status)

    @mcp.tool()
    async def get_tour_line(tour_id: int) -> dict[str, Any]:
        """Geometrie simplifiee d'un tour (polyligne legere, alternative a get_tour_coordinates).

        Args:
            tour_id: ID du tour.
        """
        return await client.get(f"{WWW_V007}/tours/{tour_id}/tour_line")

    @mcp.tool()
    async def geocode(
        query: str,
        limit: int = 5,
        lang: str = "fr",
        near_lat: float | None = None,
        near_lng: float | None = None,
    ) -> list[dict[str, Any]]:
        """Trouver les coordonnees d'un lieu (service Photon de Komoot, base OpenStreetMap).

        A utiliser avant plan_route / find_smart_tours quand on part d'un nom de lieu.

        Args:
            query: nom du lieu ou adresse (ex: 'Lac Blanc, Orbey').
            limit: nombre de resultats.
            lang: langue des resultats ('fr', 'en', 'de').
            near_lat: latitude pour privilegier les resultats proches.
            near_lng: longitude pour privilegier les resultats proches.
        """
        data = await client.get_public(
            f"{PHOTON_BASE}/api/", q=query, limit=limit, lang=lang, lat=near_lat, lon=near_lng,
        )
        return [_feature(f) for f in data.get("features", [])]

    @mcp.tool()
    async def reverse_geocode(lat: float, lng: float, lang: str = "fr") -> list[dict[str, Any]]:
        """Nom du lieu le plus proche de coordonnees (geocodage inverse Photon).

        Args:
            lat: latitude.
            lng: longitude.
            lang: langue des resultats.
        """
        data = await client.get_public(f"{PHOTON_BASE}/reverse", lat=lat, lon=lng, lang=lang)
        return [_feature(f) for f in data.get("features", [])]


def _feature(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties", {})
    lng, lat = feature.get("geometry", {}).get("coordinates", [None, None])
    return {
        "name": props.get("name"),
        "lat": lat,
        "lng": lng,
        "type": props.get("osm_value") or props.get("type"),
        "street": props.get("street"),
        "housenumber": props.get("housenumber"),
        "postcode": props.get("postcode"),
        "city": props.get("city"),
        "county": props.get("county"),
        "state": props.get("state"),
        "country": props.get("country"),
    }
