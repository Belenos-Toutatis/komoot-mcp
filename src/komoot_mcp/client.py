"""Komoot REST client — async httpx wrapper with auto-reauth and retries."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .auth import KomootAuth
from .logging_setup import get_logger

_log = get_logger()

API_BASE = "https://api.komoot.de/v007"
API_V006 = "https://api.komoot.de/v006"
WWW_BASE = "https://www.komoot.com/api"
WWW_V007 = f"{WWW_BASE}/v007"
PHOTON_BASE = "https://photon.komoot.io"

USER_AGENT = "komoot-mcp/0.2.0 (+https://github.com/Belenos-Toutatis/komoot-mcp)"
HAL_JSON = "application/hal+json, application/json;q=0.9, */*;q=0.8"

# Codes sur lesquels un GET est rejoue (meme logique que kompy 0.1)
_RETRY_STATUSES = {429, 502, 503, 504}
_MAX_RETRIES = 3


class KomootError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Komoot API {status}: {body}")
        self.status = status
        self.body = body


class KomootClient:
    def __init__(self, auth: KomootAuth | None = None) -> None:
        self._auth = auth or KomootAuth()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=10),
            headers={"User-Agent": USER_AGENT, "Accept": HAL_JSON},
        )

    @property
    def user_id(self) -> str:
        return self._auth.user_id

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        data: Any = None,
        files: dict | None = None,
        headers: dict | None = None,
        raw: bool = False,
        auth: bool = True,
        with_status: bool = False,
    ) -> Any:
        """Effectue une requete HTTP avec Basic Auth, re-auth sur 401 et retry sur 429/5xx (GET).

        with_status=True renvoie (status_code, corps) au lieu du corps seul.
        """
        reauthed = False
        retries = 0
        while True:
            t0 = time.time()
            try:
                resp = await self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    files=files,
                    headers=headers,
                    auth=self._auth.auth_tuple() if auth else None,
                )
            except httpx.TransportError as exc:
                if method == "GET" and retries < _MAX_RETRIES:
                    retries += 1
                    await asyncio.sleep(0.5 * 2 ** retries)
                    continue
                raise KomootError(0, f"transport error: {exc!r}") from exc
            dt_ms = int((time.time() - t0) * 1000)
            # Extraire un path court pour le log
            short_path = url.replace(API_BASE, "").replace(WWW_BASE, "")
            _log.info(
                "http",
                extra={
                    "event": "http",
                    "method": method,
                    "path": short_path,
                    "status": resp.status_code,
                    "duration_ms": dt_ms,
                    "attempt": retries,
                },
            )
            if resp.status_code == 401 and auth and not reauthed:
                _log.info("reauth", extra={"event": "reauth", "reason": "401 received"})
                self._auth.refresh()
                reauthed = True
                continue
            if resp.status_code in _RETRY_STATUSES and method == "GET" and retries < _MAX_RETRIES:
                retries += 1
                try:
                    wait = float(resp.headers.get("retry-after", ""))
                except ValueError:
                    wait = 0.5 * 2 ** retries
                _log.info("retry", extra={"event": "retry", "status": resp.status_code,
                                          "retry_after_s": wait})
                await asyncio.sleep(min(wait, 30))
                continue
            if resp.status_code >= 400:
                body = resp.text[:800]
                _log.error(
                    "http_error",
                    extra={
                        "event": "http_error",
                        "method": method,
                        "path": short_path,
                        "status": resp.status_code,
                        "body": body,
                    },
                )
                raise KomootError(resp.status_code, body)
            if raw:
                body = resp.content
            elif resp.status_code == 204 or not resp.content:
                body = None
            elif "json" in resp.headers.get("content-type", ""):
                body = resp.json()
            else:
                body = resp.content
            return (resp.status_code, body) if with_status else body

    # ── Convenience wrappers ─────────────────────────────────────────────

    async def get(self, path: str, raw: bool = False, **params) -> Any:
        url = f"{API_BASE}{path}" if path.startswith("/") else path
        clean = {k: v for k, v in params.items() if v is not None}
        return await self.request("GET", url, params=clean, raw=raw)

    async def get_www(self, path: str, raw: bool = False, **params) -> Any:
        """Requete via www.komoot.com/api (pour routing/import/decouverte)."""
        url = f"{WWW_BASE}{path}" if path.startswith("/") else path
        clean = {k: v for k, v in params.items() if v is not None}
        return await self.request("GET", url, params=clean, raw=raw)

    async def get_public(self, url: str, raw: bool = False, **params) -> Any:
        """GET sans authentification (Photon, liens de partage)."""
        clean = {k: v for k, v in params.items() if v is not None}
        return await self.request("GET", url, params=clean, raw=raw, auth=False)

    async def post(self, path: str, *, json_body: Any = None,
                   data: Any = None, files: dict | None = None,
                   headers: dict | None = None, params: dict | None = None,
                   with_status: bool = False) -> Any:
        url = f"{API_BASE}{path}" if path.startswith("/") else path
        return await self.request("POST", url, json_body=json_body, data=data,
                                  files=files, headers=headers, params=params,
                                  with_status=with_status)

    async def post_www(self, path: str, *, json_body: Any = None,
                       data: Any = None, files: dict | None = None,
                       headers: dict | None = None, params: dict | None = None) -> Any:
        url = f"{WWW_BASE}{path}" if path.startswith("/") else path
        return await self.request("POST", url, json_body=json_body, data=data,
                                  files=files, headers=headers, params=params)

    async def patch(self, path: str, **fields) -> Any:
        url = f"{API_BASE}{path}" if path.startswith("/") else path
        return await self.request("PATCH", url, json_body={k: v for k, v in fields.items() if v is not None})

    async def delete(self, path: str, params: dict | None = None) -> Any:
        url = f"{API_BASE}{path}" if path.startswith("/") else path
        return await self.request("DELETE", url, params=params)
