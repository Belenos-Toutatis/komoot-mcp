"""MCP tools for uploading tours to Komoot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..client import KomootClient


def register(mcp, client: KomootClient) -> None:
    @mcp.tool()
    async def upload_tour(
        gpx_content: str | None = None,
        file_path: str | None = None,
        sport: str = "hike",
        tour_name: str | None = None,
        status: str | None = "private",
    ) -> dict[str, Any]:
        """Uploader une activite enregistree sur Komoot (GPX, FIT ou TCX).

        Fournir soit gpx_content (texte GPX), soit file_path (fichier local .gpx/.fit/.tcx,
        recommande pour les gros fichiers et les FIT binaires).

        Args:
            gpx_content: contenu d'un fichier GPX (texte XML).
            file_path: chemin d'un fichier .gpx, .fit ou .tcx.
            sport: type de sport ('hike', 'touringbicycle', 'mtb', 'racebicycle',
                   'jogging', 'mountaineering', 'running', ...).
            tour_name: nom du tour (optionnel).
            status: 'private', 'friends' ou 'public' (applique apres l'upload,
                    Komoot l'ignorant a la creation). None = defaut du compte.

        Returns:
            Le tour cree, avec 'duplicate': True si Komoot a reconnu un fichier deja importe.
        """
        if (gpx_content is None) == (file_path is None):
            raise ValueError("Fournir exactement un de gpx_content ou file_path.")
        if file_path:
            path = Path(file_path).expanduser()
            data_type = path.suffix.lower().lstrip(".")
            if data_type not in ("gpx", "fit", "tcx"):
                raise ValueError(f"Extension non supportee : {path.suffix} (gpx, fit ou tcx).")
            body = path.read_bytes()
        else:
            data_type = "gpx"
            body = gpx_content.encode("utf-8")

        code, result = await client.post(
            "/tours/",
            data=body,
            headers={"Content-Type": "application/octet-stream"},
            params={k: v for k, v in {"data_type": data_type, "sport": sport,
                                      "name": tour_name}.items() if v},
            with_status=True,
        )
        if not isinstance(result, dict):
            return {"raw": str(result)[:500]}
        result["duplicate"] = code == 202
        # Komoot ignore sport/nom/visibilite a l'upload dans certains cas : on les reapplique
        fixes = {"name": tour_name if tour_name and result.get("name") != tour_name else None,
                 "sport": sport if result.get("sport") != sport else None,
                 "status": status if status and result.get("status") != status else None}
        if "id" in result and not result["duplicate"] and any(fixes.values()):
            await client.patch(f"/tours/{result['id']}", **fixes)
            result.update({k: v for k, v in fixes.items() if v})
        return result
