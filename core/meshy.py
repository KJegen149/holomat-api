"""
Meshy direct-API client — Phase 11 item 7 follow-up.

Wraps Meshy's openapi/v1 endpoints for use cases that don't fit the
Cloudflare worker proxy: namely, listing every image-to-3D task on the
account so the user can browse and import any completed model, not only
ones submitted through Holomat's Gallery.

Auth is a Meshy API key in `MESHY_API_KEY` — separate from CF_API_KEY,
which is the Cloudflare worker's own auth. Both can coexist.

Public surface:
- `is_configured()`
- `list_image_to_3d(status, page, page_size, sort_by)` → list of tasks
- `get_image_to_3d(task_id)`                          → single task detail
"""
import os
from typing import Optional

import httpx

from core.logger import get_logger

log = get_logger(__name__)

_BASE = "https://api.meshy.ai"


def _api_key() -> str:
    return os.getenv("MESHY_API_KEY", "")


def is_configured() -> bool:
    return bool(_api_key())


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Accept": "application/json"}


async def list_image_to_3d(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
    sort_by: str = "-created_at",
) -> dict:
    """Return a page of the account's Image-to-3D tasks (newest first by default)."""
    if not is_configured():
        raise RuntimeError("MESHY_API_KEY not set")

    params: dict[str, str | int] = {
        "page": page,
        "page_size": min(max(page_size, 1), 50),
        "sort_by": sort_by,
    }
    if status:
        params["status"] = status.upper()

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{_BASE}/openapi/v1/image-to-3d",
            params=params,
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()

    # Meshy returns either {result: [...], total: N} or a bare list depending
    # on endpoint version. Normalize.
    tasks_raw = data.get("result") if isinstance(data, dict) else data
    if not isinstance(tasks_raw, list):
        tasks_raw = []
    tasks = [_normalize_task(t) for t in tasks_raw]
    total = data.get("total") if isinstance(data, dict) else len(tasks)
    return {"tasks": tasks, "total": total, "page": page}


async def get_image_to_3d(task_id: str) -> dict:
    """Fetch one task's full detail (including model_urls when SUCCEEDED)."""
    if not is_configured():
        raise RuntimeError("MESHY_API_KEY not set")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{_BASE}/openapi/v1/image-to-3d/{task_id}",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


def _normalize_task(t: dict) -> dict:
    """Slim each task down to the fields the UI cares about."""
    return {
        "id": t.get("id"),
        "status": str(t.get("status", "")).upper(),
        "progress": int(t.get("progress", 0) or 0),
        "prompt": t.get("prompt") or "",
        "thumbnail_url": t.get("thumbnail_url"),
        "image_url": (t.get("image_urls") or [None])[0] if isinstance(t.get("image_urls"), list) else None,
        "created_at": t.get("created_at"),
        "finished_at": t.get("finished_at"),
        "has_stl": bool((t.get("model_urls") or {}).get("stl")),
        "stl_url": (t.get("model_urls") or {}).get("stl"),
    }
