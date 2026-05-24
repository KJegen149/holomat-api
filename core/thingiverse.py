"""
Thingiverse API client — Phase 11 item 4.

Wraps the Thingiverse REST API for search-and-import. Auth is via an app
token (Authorization: Bearer <token>) issued at thingiverse.com/developers/my-apps
and stored in the `THINGIVERSE_TOKEN` env var.

Public surface used by `api/routes/sources.py`:
- `is_configured()`
- `search(query, page, per_page)`     → `{things: [...], total, page}`
- `get_files(thing_id)`                → `[{id, name, size, ...}]`
- `download_file(file_id) -> bytes`    → file body
- `get_thing(thing_id)`                → metadata (for the sidecar)
"""
import os
from typing import Optional
from urllib.parse import quote

import httpx

from core.logger import get_logger

log = get_logger(__name__)

_BASE = "https://api.thingiverse.com"


def _token() -> str:
    return os.getenv("THINGIVERSE_TOKEN", "")


def is_configured() -> bool:
    return bool(_token())


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


async def search(query: str, page: int = 1, per_page: int = 20) -> dict:
    """Search Thingiverse Things. Returns a normalized envelope."""
    if not is_configured():
        raise RuntimeError("THINGIVERSE_TOKEN not set")

    params = {
        "type": "things",
        "page": page,
        "per_page": per_page,
        "sort": "relevant",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{_BASE}/search/{quote(query, safe='')}",
            params=params,
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()

    # Thingiverse's `/search/{term}` returns `{hits: [...], total: N}`.
    hits = data.get("hits") if isinstance(data, dict) else data
    if not isinstance(hits, list):
        hits = []

    things = [_normalize_thing(t) for t in hits]
    total = data.get("total") if isinstance(data, dict) else len(things)
    return {"things": things, "total": total, "page": page}


def _normalize_thing(t: dict) -> dict:
    creator = t.get("creator") or {}
    thumb = (
        t.get("thumbnail")
        or t.get("preview_image")
        or t.get("default_image", {}).get("url")
    )
    return {
        "id": t.get("id"),
        "name": t.get("name"),
        "creator": creator.get("name") or creator.get("first_name") or "unknown",
        "thumbnail_url": thumb,
        "public_url": t.get("public_url") or f"https://www.thingiverse.com/thing:{t.get('id')}",
        "like_count": t.get("like_count"),
        "is_nsfw": t.get("is_nsfw", False),
    }


async def get_thing(thing_id: int) -> dict:
    if not is_configured():
        raise RuntimeError("THINGIVERSE_TOKEN not set")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{_BASE}/things/{thing_id}", headers=_headers())
        r.raise_for_status()
        return r.json()


async def get_files(thing_id: int) -> list[dict]:
    """List downloadable files attached to a Thing, STL files first."""
    if not is_configured():
        raise RuntimeError("THINGIVERSE_TOKEN not set")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{_BASE}/things/{thing_id}/files", headers=_headers())
        r.raise_for_status()
        files = r.json() or []

    normalized = [
        {
            "id": f.get("id"),
            "name": f.get("name", ""),
            "size": f.get("size"),
            "is_stl": (f.get("name", "").lower().endswith(".stl")),
            "download_url": f.get("download_url"),
            "public_url": f.get("public_url"),
        }
        for f in files
    ]
    # STL first, then everything else, both by name.
    normalized.sort(key=lambda f: (not f["is_stl"], f["name"].lower()))
    return normalized


async def download_file(file_id: int) -> tuple[bytes, Optional[str]]:
    """Fetch a file's bytes via the Thingiverse API. Returns (data, filename)."""
    if not is_configured():
        raise RuntimeError("THINGIVERSE_TOKEN not set")
    # `/files/{id}/download` 302s to a presigned URL — follow it.
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        r = await client.get(f"{_BASE}/files/{file_id}/download", headers=_headers())
        r.raise_for_status()
        # Try to pull the filename out of Content-Disposition
        filename = None
        disp = r.headers.get("content-disposition", "")
        if "filename=" in disp:
            filename = disp.split("filename=", 1)[1].strip().strip('"').strip("'")
        return r.content, filename
