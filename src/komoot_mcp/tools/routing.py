"""MCP tools for Komoot route planning and import.

Ces endpoints passent par www.komoot.com/api (pas api.komoot.de).
Inspires du projet export-komoot (Go) de pieterclaerhout.
"""

from __future__ import annotations

import math
from typing import Any

from ..client import KomootClient, KomootError


# ── Shared helper functions (module-level, no side effects) ────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _segment_km(coords: list[dict[str, Any]], from_i: int, to_i: int) -> float:
    """Sum of Haversine distances between consecutive coords from from_i to to_i."""
    total = 0.0
    for i in range(max(0, from_i), min(to_i, len(coords) - 1)):
        c1 = coords[i]
        c2 = coords[i + 1]
        try:
            total += _haversine_km(
                float(c1.get("lat", 0)), float(c1.get("lng", 0)),
                float(c2.get("lat", 0)), float(c2.get("lng", 0)),
            )
        except (TypeError, ValueError):
            pass
    return total


def _compute_singletrail(
    wt_items: list[dict[str, Any]],
    coord_items: list[dict[str, Any]],
    total_km: float,
) -> dict[str, Any]:
    """Compute singletrail breakdown from way-type items and coordinates.

    Extracts trail_d1..trail_d5 segments, merges overlapping intervals,
    calculates Haversine distance for each type, and returns total + percentage.

    Returns {'available': False} when no trail_d* data is present.
    """
    if not wt_items or not coord_items:
        return {"available": False}

    # Filter trail_d1..trail_d5
    trail_by_type: dict[str, list[dict[str, Any]]] = {}
    for item in wt_items:
        if not isinstance(item, dict):
            continue
        element = item.get("element", "")
        if not isinstance(element, str) or not element.startswith("wt#trail_d"):
            continue
        key = element.replace("wt#", "")
        trail_by_type.setdefault(key, []).append({
            "from": item.get("from"),
            "to": item.get("to"),
        })

    if not trail_by_type:
        return {"available": False}

    st_out: dict[str, Any] = {}
    st_total_km = 0.0

    for trail_key in sorted(trail_by_type.keys()):
        intervals = trail_by_type[trail_key]
        intervals.sort(key=lambda x: int(x.get("from", 0) or 0))

        # Merge overlapping intervals
        merged: list[dict[str, Any]] = []
        for iv in intervals:
            if not merged:
                merged.append(dict(iv))
            else:
                last = merged[-1]
                fv = int(iv.get("from") or 0)
                lv = int(iv.get("to") or 0)
                lf = int(last.get("from") or 0)
                lt = int(last.get("to") or 0)
                if fv <= lt:
                    last["to"] = max(lt, lv)
                else:
                    merged.append(dict(iv))

        # Calculate distance
        d_km: float | None = None
        if coord_items and merged:
            try:
                seg_d = 0.0
                for m in merged:
                    fi = int(m.get("from") or 0)
                    ti = int(m.get("to") or 0)
                    if 0 <= fi < ti <= len(coord_items):
                        seg_d += _segment_km(coord_items, fi, ti)
                if seg_d > 0:
                    d_km = round(seg_d, 2)
            except (TypeError, ValueError, IndexError):
                d_km = None

        entry: dict[str, Any] = {
            "segments": len(intervals),
            "from_to": [[int(iv["from"]), int(iv["to"])] for iv in intervals],
        }
        if d_km is not None:
            entry["distance_km"] = d_km
            st_total_km += d_km
        st_out[trail_key] = entry

    # Ordered by d1..d5 (only existing types)
    ordered: dict[str, Any] = {}
    for d in range(1, 6):
        key = f"trail_d{d}"
        if key in st_out:
            ordered[key] = st_out[key]

    if st_total_km > 0:
        ordered["singletrail_total_km"] = round(st_total_km, 2)
        if total_km and total_km > 0:
            ordered["singletrail_percentage"] = round(
                st_total_km / total_km * 100, 1
            )

    return ordered


def _compact_route_summary(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert raw plan_route API response into a compact route summary.

    Uses the same extraction pattern as import_gpx_file, enriched with
    singletrail data from _embedded way-type items + coordinates.
    No additional API calls are made.
    """
    result: dict[str, Any] = {}

    # Distance
    if "distance" in raw:
        d = float(raw["distance"])
        result["distance_km"] = round(d / 1000.0, 2)
        result["distance_m"] = round(d, 1)

    # Elevation
    if "elevation_up" in raw:
        result["elevation_up_m"] = round(float(raw["elevation_up"]), 1)
    if "elevation_down" in raw:
        result["elevation_down_m"] = round(float(raw["elevation_down"]), 1)

    # Duration
    if "duration" in raw:
        dur_s = int(float(raw["duration"]))
        result["duration_seconds"] = dur_s
        h = dur_s // 3600
        m = (dur_s % 3600) // 60
        result["duration"] = f"{h}h {m}m" if h else f"{m}m"

    # Difficulty (grade + T/C)
    diff = raw.get("difficulty")
    if isinstance(diff, dict):
        if diff.get("grade"):
            result["difficulty"] = diff["grade"]
        tech_raw = diff.get("explanation_technical", "")
        if tech_raw and isinstance(tech_raw, str) and "#" in tech_raw:
            result["technical_difficulty"] = tech_raw.split("#", 1)[1].upper()
        fit_raw = diff.get("explanation_fitness", "")
        if fit_raw and isinstance(fit_raw, str) and "#" in fit_raw:
            result["fitness_difficulty"] = fit_raw.split("#", 1)[1].upper()

    total_km = result.get("distance_km", 0)

    # Way types (percentage + approximated km from total distance)
    summary = raw.get("summary", {})
    if isinstance(summary, dict):
        wts = summary.get("way_types", [])
        if isinstance(wts, list):
            result["way_types"] = {
                str(item["type"]).replace("wt#", ""): {
                    "percentage": round(float(item["amount"]) * 100, 1),
                    "distance_km": round(float(item["amount"]) * total_km, 2)
                    if total_km > 0 else 0.0,
                }
                for item in wts
                if isinstance(item, dict) and "type" in item and "amount" in item
            }

        # Surfaces (percentage + approximated km from total distance)
        surfaces = summary.get("surfaces", [])
        if isinstance(surfaces, list):
            result["surfaces"] = {
                str(item["type"]).replace("sm#", ""): {
                    "percentage": round(float(item["amount"]) * 100, 1),
                    "distance_km": round(float(item["amount"]) * total_km, 2)
                    if total_km > 0 else 0.0,
                }
                for item in surfaces
                if isinstance(item, dict) and "type" in item and "amount" in item
            }

    # Singletrail (from _embedded.way_types.items + coordinates)
    embedded = raw.get("_embedded", {})
    if isinstance(embedded, dict):
        wt_container = embedded.get("way_types", {})
        wt_items: list[dict[str, Any]] = []
        if isinstance(wt_container, dict):
            wt_items = wt_container.get("items", [])
        elif isinstance(wt_container, list):
            wt_items = wt_container
        if not isinstance(wt_items, list):
            wt_items = []

        coord_container = embedded.get("coordinates", {})
        coord_items: list[dict[str, Any]] = []
        if isinstance(coord_container, dict):
            coord_items = coord_container.get("items", [])
        elif isinstance(coord_container, list):
            coord_items = coord_container
        if not isinstance(coord_items, list):
            coord_items = []

        result["singletrail"] = _compute_singletrail(
            wt_items, coord_items, total_km
        )

        # Coordinate count — NOT the full list
        if coord_items:
            result["matched_coordinates"] = len(coord_items)

    # Segments
    segs = raw.get("segments", [])
    if isinstance(segs, list):
        routed = sum(
            1 for s in segs if isinstance(s, dict) and s.get("type") == "Routed"
        )
        manual = sum(
            1 for s in segs if isinstance(s, dict) and s.get("type") == "Manual"
        )
        result["segments"] = {"routed": routed, "manual": manual}

    # Tour information
    ti = raw.get("tour_information", [])
    if isinstance(ti, list) and ti:
        info_list: list[dict[str, Any]] = []
        for item in ti:
            if isinstance(item, dict) and item.get("type"):
                segs = item.get("segments", [])
                info_list.append({
                    "type": str(item["type"]),
                    "segments": len(segs) if isinstance(segs, list) else 0,
                })
        result["tour_information"] = info_list

    return result


def register(mcp, client: KomootClient) -> None:
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

        # Etape 2 : extraire l'item importe (pas le wrapper complet)
        try:
            item = import_result["_embedded"]["items"][0]
        except (KeyError, IndexError, TypeError):
            return {
                "error": "Komoot returned no import item",
                "response": import_result,
            }

        # Etape 3 : route matching
        matched = await client.post_www(
            "/routing/import/tour",
            json_body=item,
            params={
                "sport": sport,
                "_embedded": "way_types,surfaces,directions,coordinates",
            },
        )
        return matched

    @mcp.tool()
    async def import_gpx_file(
        file_path: str,
        sport: str = "mtb",
    ) -> dict[str, Any]:
        """Import and analyze a local GPX file using Komoot's matching service.

        Reads a local GPX file, matches it against Komoot's routing network,
        and returns a compact route analysis. This tool does not create a
        planned Komoot tour.

        Args:
            file_path: path to the local GPX file.
            sport: sport type used for Komoot matching (default: mtb).
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                gpx_content = f.read()
        except FileNotFoundError:
            return {"error": f"File not found: {file_path}"}
        except Exception as e:
            return {"error": f"Failed to read GPX file: {str(e)}"}

        # First upload the GPX to Komoot's routing import service.
        import_result = await client.post_www(
            "/routing/import/files/",
            data=gpx_content.encode("utf-8"),
            headers={"Content-Type": "application/gpx+xml"},
            params={"data_type": "gpx"},
        )

        if not isinstance(import_result, dict):
            return {"raw": str(import_result)}

        try:
            item = import_result["_embedded"]["items"][0]
        except (KeyError, IndexError, TypeError):
            return {
                "error": "Komoot returned no import item",
                "response": import_result,
            }

        # Match the imported track against Komoot's routing network.
        matched = await client.post_www(
            "/routing/import/tour",
            json_body=item,
            params={
                "sport": sport,
                "_embedded": "way_types,surfaces,directions,coordinates",
            },
        )

        if not isinstance(matched, dict):
            return {"raw": str(matched)}

        # The actual tour data lives under _embedded.matched, not at top level.
        tour = matched.get("_embedded", {})
        if not isinstance(tour, dict):
            tour = {}
        tour = tour.get("matched", {})

        result: dict[str, Any] = {
            "file_path": file_path,
            "sport": tour.get("sport", sport),
            "status": "success",
        }

        # Basic route information.
        if "name" in tour:
            result["name"] = tour["name"]

        if "distance" in tour:
            result["distance_km"] = round(float(tour["distance"]) / 1000.0, 2)

        if "elevation_up" in tour:
            result["elevation_up_m"] = round(float(tour["elevation_up"]), 1)

        if "elevation_down" in tour:
            result["elevation_down_m"] = round(float(tour["elevation_down"]), 1)

        if "duration" in tour:
            duration_seconds = int(float(tour["duration"]))
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60

            if hours:
                result["duration"] = f"{hours}h {minutes}m"
            else:
                result["duration"] = f"{minutes}m"

        difficulty = tour.get("difficulty")
        if isinstance(difficulty, dict) and difficulty.get("grade"):
            result["difficulty"] = difficulty["grade"]

        # Komoot already provides normalized surface and way-type percentages.
        summary = tour.get("summary", {})
        if isinstance(summary, dict):
            surfaces = summary.get("surfaces", [])
            if isinstance(surfaces, list):
                result["surfaces"] = {
                    str(item["type"]).replace("sm#", ""): round(
                        float(item["amount"]) * 100, 1
                    )
                    for item in surfaces
                    if isinstance(item, dict)
                    and "type" in item
                    and "amount" in item
                }

            way_types = summary.get("way_types", [])
            if isinstance(way_types, list):
                result["way_types"] = {
                    str(item["type"]).replace("wt#", ""): round(
                        float(item["amount"]) * 100, 1
                    )
                    for item in way_types
                    if isinstance(item, dict)
                    and "type" in item
                    and "amount" in item
                }

        # Extract Komoot's technical and fitness difficulty ratings.
        if isinstance(difficulty, dict):
            tech_raw = difficulty.get("explanation_technical", "")
            if tech_raw and isinstance(tech_raw, str) and "#" in tech_raw:
                result["technical_difficulty"] = tech_raw.split("#", 1)[1].upper()
            fit_raw = difficulty.get("explanation_fitness", "")
            if fit_raw and isinstance(fit_raw, str) and "#" in fit_raw:
                result["fitness_difficulty"] = fit_raw.split("#", 1)[1].upper()

        # Highlight special route information such as off-grid sections
        # or places where Komoot recommends dismounting.
        tour_information = tour.get("tour_information", [])
        if isinstance(tour_information, list):
            special_sections = []

            for info in tour_information:
                if not isinstance(info, dict):
                    continue

                info_type = info.get("type")
                segments = info.get("segments", [])

                if info_type:
                    special_sections.append({
                        "type": str(info_type),
                        "segments": len(segments)
                        if isinstance(segments, list)
                        else 0,
                    })

            if special_sections:
                result["tour_information"] = special_sections

        # Number of matched coordinates, without returning thousands of
        # coordinates to the language model.
        tour_embedded = tour.get("_embedded", {})
        if isinstance(tour_embedded, dict):
            coordinates = tour_embedded.get("coordinates", {})
            if isinstance(coordinates, dict):
                coordinate_items = coordinates.get("items", [])
                if isinstance(coordinate_items, list):
                    result["matched_coordinates"] = len(coordinate_items)

        # Report routed/manual portions of the imported track.
        segments = tour.get("segments", [])
        if isinstance(segments, list):
            routed = sum(
                1 for segment in segments
                if isinstance(segment, dict) and segment.get("type") == "Routed"
            )
            manual = sum(
                1 for segment in segments
                if isinstance(segment, dict) and segment.get("type") == "Manual"
            )

            result["segments"] = {
                "routed": routed,
                "manual": manual,
            }

        # parent_tour_id: the imported file's tour ID, if assigned by Komoot.
        # This is present when the matched route is linked to an existing
        # Komoot tour (e.g., a previously created planned tour).
        if "id" in tour:
            result["parent_tour_id"] = tour["id"]

        return result

    @mcp.tool()
    async def plan_route(
        coordinates: list[list[float]],
        sport: str = "hike",
        compact: bool = False,
    ) -> dict[str, Any]:
        """Planifier un itineraire Komoot a partir de waypoints.

        Args:
            coordinates: liste de [lat, lng] pour les points de passage
                         (ex: [[48.5734, 7.7521], [48.5801, 7.7612]]).
            sport: type de sport ('hike', 'touringbicycle', 'mtb', 'racebicycle', 'jogging').
            compact: si True, renvoie un resume compact de la route
                     (distance, elevation, duree, difficulte, way_types,
                     surfaces, singletrail, segments) au lieu de la
                     reponse complete de l'API Komoot. Defaut: False
                     (comportement historique, retrocompatible).
        """
        # Build path (indexed waypoints) and segments (Routed geometry between consecutive points)
        path = []
        segments = []
        for i, coord in enumerate(coordinates):
            point = {"lat": coord[0], "lng": coord[1], "alt": 0.0}
            path.append({"location": point, "index": i})
            if i > 0:
                prev_coord = coordinates[i - 1]
                prev_point = {"lat": prev_coord[0], "lng": prev_coord[1], "alt": 0.0}
                segments.append({"type": "Routed", "geometry": [prev_point, point]})

        result = await client.post_www(
            "/routing/tour",
            json_body={
                "path": path,
                "segments": segments,
                "sport": sport,
            },
            params={
                "_embedded": "coordinates,way_types,surfaces,directions",
            },
        )
        if compact:
            return _compact_route_summary(result)
        return result

    def _prepare_planned_tour_payload(
        route_data: dict[str, Any],
        name: str = "Tour planifie",
        sport: str = "hike",
    ) -> dict[str, Any]:
        """Normalise route_data en payload pour POST /v007/tours/?reroute=true.

        Si route_data est le resultat brut d'import_gpx_route (contenant
        _embedded.matched), extrait automatiquement le tour matche.
        Agit sur une copie, ne mute jamais l'original.

        Args:
            route_data: resultat de import_gpx_route() ou plan_route().
            name: nom du tour planifie.
            sport: type de sport.
        """
        payload = dict(route_data)
        # Si c'est le resultat brut de import_gpx_route
        embedded = payload.get("_embedded")
        if isinstance(embedded, dict) and "matched" in embedded:
            payload = dict(embedded["matched"])
        payload["name"] = name
        payload["sport"] = sport
        # Remove fields that would break the POST
        for key in list(payload.keys()):
            if key in ("_links", "uri"):
                del payload[key]
        return payload

    @mcp.tool()
    async def create_planned_tour(
        route_data: dict[str, Any],
        name: str = "Tour planifie",
        sport: str = "hike",
    ) -> dict[str, Any]:
        """Creer un tour planifie sur Komoot a partir d'un resultat de plan_route ou import_gpx_route.

        Args:
            route_data: resultat JSON de plan_route() ou import_gpx_route().
            name: nom du tour planifie.
            sport: type de sport.
        """
        payload = _prepare_planned_tour_payload(route_data, name, sport)
        return await client.request(
            "POST",
            f"https://api.komoot.de/v007/tours/",
            json_body=payload,
            params={"reroute": "true"},
        )

    @mcp.tool()
    async def analyze_komoot_tour(tour_id: int) -> dict[str, Any]:
        """Analyse detaillee d'une tour existante (singletrail, difficulte, surface, etc.).

        Args:
            tour_id: ID du tour Komoot existant.
        """
        try:
            tour = await client.get(
                f"/tours/{tour_id}",
                _embedded="way_types,surfaces,coordinates",
            )
        except KomootError as e:
            return {"tour_id": tour_id, "status": "error", "error": str(e)}

        if not isinstance(tour, dict):
            return {"tour_id": tour_id, "status": "error", "error": "Unexpected API response"}

        result: dict[str, Any] = {
            "tour_id": tour_id,
            "status": "success",
        }

        # ── Basic tour info ──────────────────────────────────────────────
        if tour.get("name"):
            result["name"] = tour["name"]
        if tour.get("sport"):
            result["sport"] = tour["sport"]
        if tour.get("distance"):
            result["distance_km"] = round(float(tour["distance"]) / 1000.0, 2)
        if "elevation_up" in tour:
            result["elevation_up_m"] = round(float(tour["elevation_up"]), 1)
        if "elevation_down" in tour:
            result["elevation_down_m"] = round(float(tour["elevation_down"]), 1)
        if tour.get("duration"):
            dur_s = int(float(tour["duration"]))
            h = dur_s // 3600
            m = (dur_s % 3600) // 60
            result["duration"] = f"{h}h {m}m" if h else f"{m}m"
        if "constitution" in tour:
            result["constitution"] = tour["constitution"]

        # ── Difficulty ────────────────────────────────────────────────────
        diff = tour.get("difficulty")
        if isinstance(diff, dict):
            if diff.get("grade"):
                result["difficulty"] = diff["grade"].upper()
            tech_raw = diff.get("explanation_technical", "")
            if tech_raw and isinstance(tech_raw, str) and "#" in tech_raw:
                result["technical_difficulty"] = tech_raw.split("#", 1)[1].upper()
            fit_raw = diff.get("explanation_fitness", "")
            if fit_raw and isinstance(fit_raw, str) and "#" in fit_raw:
                result["fitness_difficulty"] = fit_raw.split("#", 1)[1].upper()

        # ── Summary (surfaces, way_types) ─────────────────────────────────
        summary = tour.get("summary")
        if isinstance(summary, dict):
            surfaces = summary.get("surfaces", [])
            if isinstance(surfaces, list):
                result["surfaces"] = {
                    s["type"].replace("sm#", ""): round(float(s["amount"]) * 100, 1)
                    for s in surfaces
                    if isinstance(s, dict) and "type" in s and "amount" in s
                }
            wts = summary.get("way_types", [])
            if isinstance(wts, list):
                result["way_types"] = {
                    w["type"].replace("wt#", ""): round(float(w["amount"]) * 100, 1)
                    for w in wts
                    if isinstance(w, dict) and "type" in w and "amount" in w
                }

        # ── Tour information ──────────────────────────────────────────────
        ti = tour.get("tour_information", [])
        if isinstance(ti, list) and ti:
            info_list: list[dict[str, Any]] = []
            for item in ti:
                if isinstance(item, dict) and item.get("type"):
                    segs = item.get("segments", [])
                    info_list.append({
                        "type": str(item["type"]),
                        "segments": len(segs) if isinstance(segs, list) else 0,
                    })
            result["tour_information"] = info_list

        # ── Segments ──────────────────────────────────────────────────────
        segs = tour.get("segments", [])
        if isinstance(segs, list):
            routed = sum(1 for s in segs if isinstance(s, dict) and s.get("type") == "Routed")
            manual = sum(1 for s in segs if isinstance(s, dict) and s.get("type") == "Manual")
            result["segments"] = {"routed": routed, "manual": manual}

        # ── Singletrail analysis (trail_d1..trail_d5) ─────────────────────
        embedded = tour.get("_embedded", {})
        if not isinstance(embedded, dict):
            embedded = {}

        # Way-type items
        wt_container = embedded.get("way_types", {})
        wt_items: list[dict[str, Any]] = []
        if isinstance(wt_container, dict):
            wt_items = wt_container.get("items", [])
        elif isinstance(wt_container, list):
            wt_items = wt_container
        if not isinstance(wt_items, list):
            wt_items = []

        # Coordinates
        coord_container = embedded.get("coordinates", {})
        coord_items: list[dict[str, Any]] = []
        if isinstance(coord_container, dict):
            coord_items = coord_container.get("items", [])
        elif isinstance(coord_container, list):
            coord_items = coord_container
        if not isinstance(coord_items, list):
            coord_items = []

        total_km = result.get("distance_km", 0)
        result["singletrail"] = _compute_singletrail(wt_items, coord_items, total_km)

        # Coordinate count (not the actual list)
        if coord_items:
            result["matched_coordinates"] = len(coord_items)

        return result

    @mcp.tool()
    async def create_planned_tour_from_gpx(
        file_path: str,
        sport: str = "mtb",
        name: str = "GPX import",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Import a local GPX file and prepare a planned Komoot tour.

        Workflow:
          1. Upload GPX  →  POST /routing/import/files/
          2. Match route →  POST /routing/import/tour
          3. Prepare payload for POST /v007/tours/?reroute=true

        The write API call is ONLY executed when dry_run=False.
        Default: dry_run=True (prepares and inspects, never writes).

        Args:
            file_path: path to the local GPX file.
            sport: sport type (e.g. mtb, hike, roadbike, touringbicycle).
            name: name for the planned tour.
            dry_run: if True (default), prepare payload but do NOT create the tour.
        """
        # ── Step 1: Read GPX file ────────────────────────────────────────
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                gpx_content = f.read()
        except FileNotFoundError:
            return {"status": "error", "error": f"File not found: {file_path}"}
        except Exception as e:
            return {"status": "error", "error": f"Failed to read GPX file: {str(e)}"}

        # ── Step 2: Upload GPX ───────────────────────────────────────────
        import_result = await client.post_www(
            "/routing/import/files/",
            data=gpx_content.encode("utf-8"),
            headers={"Content-Type": "application/gpx+xml"},
            params={"data_type": "gpx"},
        )
        if not isinstance(import_result, dict):
            return {"status": "error", "raw": str(import_result)}

        try:
            item = import_result["_embedded"]["items"][0]
        except (KeyError, IndexError, TypeError):
            return {
                "status": "error",
                "error": "Komoot returned no import item",
                "response": import_result,
            }

        # ── Step 3: Match against routing network ────────────────────────
        matched = await client.post_www(
            "/routing/import/tour",
            json_body=item,
            params={
                "sport": sport,
                "_embedded": "way_types,surfaces,directions,coordinates",
            },
        )
        if not isinstance(matched, dict):
            return {"status": "error", "raw": str(matched)}

        # ── Step 4: Extract matched tour data ────────────────────────────
        matched_tour = matched.get("_embedded", {}).get("matched", {})
        if not matched_tour:
            return {"status": "error", "error": "No matched tour in response", "response": matched}

        # ── Step 5: Prepare payload ──────────────────────────────────────
        payload = _prepare_planned_tour_payload(matched, name, sport)

        # ── Step 6: Build result ─────────────────────────────────────────
        result: dict[str, Any] = {
            "status": "prepared" if dry_run else "pending",
            "file_path": file_path,
            "name": name,
            "sport": sport,
        }

        # Extract basic info for display
        if matched_tour.get("distance"):
            result["distance_km"] = round(float(matched_tour["distance"]) / 1000.0, 2)
        if "elevation_up" in matched_tour:
            result["elevation_up_m"] = round(float(matched_tour["elevation_up"]), 1)
        if "elevation_down" in matched_tour:
            result["elevation_down_m"] = round(float(matched_tour["elevation_down"]), 1)
        if matched_tour.get("duration"):
            dur_s = int(float(matched_tour["duration"]))
            h = dur_s // 3600
            m = (dur_s % 3600) // 60
            result["duration"] = f"{h}h {m}m" if h else f"{m}m"

        diff = matched_tour.get("difficulty")
        if isinstance(diff, dict):
            if diff.get("grade"):
                result["difficulty"] = diff["grade"]
            tech_raw = diff.get("explanation_technical", "")
            if tech_raw and isinstance(tech_raw, str) and "#" in tech_raw:
                result["technical_difficulty"] = tech_raw.split("#", 1)[1].upper()
            fit_raw = diff.get("explanation_fitness", "")
            if fit_raw and isinstance(fit_raw, str) and "#" in fit_raw:
                result["fitness_difficulty"] = fit_raw.split("#", 1)[1].upper()

        if dry_run:
            result["dry_run"] = True
            result["message"] = "Payload prepared. Set dry_run=False to create the tour."
            result["payload_structure"] = {
                "endpoint": "POST https://api.komoot.de/v007/tours/?reroute=true",
                "keys": list(payload.keys()),
                "name": payload.get("name"),
                "sport": payload.get("sport"),
                "segments_count": len(payload.get("segments", [])),
            }
        else:
            # ── Step 7: Create the tour (writes to Komoot!) ──────────────
            creation_result = await client.request(
                "POST",
                "https://api.komoot.de/v007/tours/",
                json_body=payload,
                params={"reroute": "true"},
            )
            if isinstance(creation_result, dict):
                tour_id = creation_result.get("id") or creation_result.get("tour_id")
                if tour_id:
                    result["status"] = "success"
                    result["tour_id"] = tour_id
                    result["komoot_tour_url"] = f"https://www.komoot.com/tour/{tour_id}"
                else:
                    result["status"] = "created"
                    result["response"] = str(creation_result)[:500]
            else:
                result["status"] = "error"
                result["response"] = str(creation_result)[:500]

        return result
