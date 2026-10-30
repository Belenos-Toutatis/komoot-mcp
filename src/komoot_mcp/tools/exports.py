"""MCP tools for exporting Komoot tours as GPX / FIT."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..client import KomootClient, KomootError


def register(mcp, client: KomootClient) -> None:
    @mcp.tool()
    async def download_tour_gpx(
        tour_id: int,
        save_path: str | None = None,
        share_token: str | None = None,
    ) -> str:
        """Telecharger un tour au format GPX (trace GPS complete).

        Args:
            tour_id: ID du tour.
            save_path: fichier ou dossier ou enregistrer le GPX. Si fourni, seul le chemin
                       est renvoye (evite de faire transiter tout le XML dans la conversation).
            share_token: jeton de partage, pour un tour prive d'un autre utilisateur.

        Returns:
            Contenu GPX en texte XML, ou chemin du fichier ecrit.
        """
        data = await client.get(f"/tours/{tour_id}.gpx", raw=True, share_token=share_token)
        if save_path:
            path = _write(save_path, f"{tour_id}.gpx", data)
            return f"GPX enregistre : {path} ({len(data)} octets)"
        return data.decode("utf-8")

    @mcp.tool()
    async def download_tour_fit(tour_id: int, save_path: str | None = None) -> str:
        """Telecharger un tour planifie au format FIT (format Garmin/ANT+).

        Komoot ne fournit le FIT que pour les tours planifies (pas les activites enregistrees).

        Args:
            tour_id: ID du tour planifie.
            save_path: fichier ou dossier ou enregistrer le FIT (recommande : le FIT est binaire).
        """
        try:
            data = await client.get(f"/tours/{tour_id}.fit", raw=True)
        except KomootError as exc:
            if exc.status in (400, 403, 404, 406):
                raise KomootError(exc.status, "FIT indisponible : Komoot ne l'exporte que pour "
                                  "les tours planifies. Utiliser download_tour_gpx.") from exc
            raise
        if save_path:
            path = _write(save_path, f"{tour_id}.fit", data)
            return f"FIT enregistre : {path} ({len(data)} octets)"
        return f"FIT recupere : {len(data)} octets pour le tour {tour_id} (fournir save_path pour l'enregistrer)"

    @mcp.tool()
    async def export_all_tours(
        dest_dir: str,
        fmt: str = "gpx",
        tour_type: str | None = None,
        sport_types: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        overwrite: bool = False,
        max_tours: int = 1000,
    ) -> dict[str, Any]:
        """Sauvegarder en masse ses tours dans un dossier (fichiers '<id>_<nom>.gpx').

        Les fichiers deja presents sont sautes sauf overwrite=True ; un echec n'arrete pas les autres.

        Args:
            dest_dir: dossier de destination (cree si besoin).
            fmt: 'gpx' ou 'fit' (FIT : tours planifies uniquement).
            tour_type: 'tour_planned', 'tour_recorded' ou None pour tous.
            sport_types: sports separes par virgule.
            start_date: date ISO minimale (ex: '2026-01-01').
            end_date: date ISO maximale.
            overwrite: re-telecharger les fichiers existants.
            max_tours: nombre maximal de tours a traiter.
        """
        if fmt not in ("gpx", "fit"):
            raise ValueError("fmt doit valoir 'gpx' ou 'fit'.")
        from .tours import _iso

        out = Path(dest_dir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        skipped: list[str] = []
        failures: dict[str, str] = {}
        page = 0
        seen = 0
        while seen < max_tours:
            result = await client.get(
                f"/users/{client.user_id}/tours/",
                type="tour_planned" if fmt == "fit" else tour_type,
                sport_types=sport_types,
                start_date=_iso(start_date),
                end_date=_iso(end_date, end_of_day=True),
                page=page,
                limit=100,
            )
            tours = result.get("_embedded", {}).get("tours", [])
            for tour in tours[: max_tours - seen]:
                seen += 1
                target = out / f"{tour['id']}_{_slug(tour.get('name', ''))}.{fmt}"
                if target.exists() and not overwrite:
                    skipped.append(target.name)
                    continue
                try:
                    data = await client.get(f"/tours/{tour['id']}.{fmt}", raw=True)
                    _atomic_write(target, data)
                    written.append(target.name)
                except KomootError as exc:
                    failures[str(tour["id"])] = f"{exc.status}: {exc.body[:120]}"
            total_pages = result.get("page", {}).get("totalPages", 0)
            page += 1
            if not tours or page >= total_pages:
                break
        return {
            "dest_dir": str(out),
            "written": len(written),
            "skipped_existing": len(skipped),
            "failures": failures,
            "files": written,
        }


def _slug(name: str) -> str:
    slug = re.sub(r"[^\w-]+", "_", name, flags=re.UNICODE).strip("_")
    return slug[:60] or "tour"


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def _write(save_path: str, default_name: str, data: bytes) -> Path:
    path = Path(save_path).expanduser()
    if path.is_dir() or save_path.endswith(("/", "\\")):
        path.mkdir(parents=True, exist_ok=True)
        path = path / default_name
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, data)
    return path
