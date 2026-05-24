"""
Model Sources routes — Phase 11.

The Model Sources tab is the home for everything that funnels printable STLs
into `scan_data/stls/`. This module owns the browser/manager view of that
shared pool; later commits add per-source import endpoints (Meshy retrieval,
Thingiverse, MakerWorld, …).

GET    /api/sources/stls               — list STLs in the pool (with sidecar metadata)
DELETE /api/sources/stls/{filename}    — delete an STL (refuses if referenced by an active job)
GET    /api/sources/meshy/jobs         — list Meshy retrieval jobs (active + history)
DELETE /api/sources/meshy/jobs/{id}    — cancel a pending Meshy job
GET    /api/sources/thingiverse/search?q=…&page=…  — search Thingiverse
GET    /api/sources/thingiverse/things/{id}/files  — list a Thing's files
POST   /api/sources/thingiverse/import — download a Thingiverse file into the pool

Per-file sidecar: an STL named `foo.stl` may have `foo.stl.meta.json` next to
it with shape `{"source": "<id>", "external_url": "...", ...}`. Import sources
write the sidecar at download time; legacy files have no sidecar and surface
as `source: "unknown"`.
"""
import json
import re
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core import thingiverse
from core.logger import get_logger
from core.meshy_jobs import meshy_jobs
from core.print_queue import print_queue

log = get_logger(__name__)
router = APIRouter()

STL_DIR = Path("scan_data/stls")

# Active states copied from core.print_queue — a job in any of these has an
# open file handle on the STL, deletion would be unsafe.
_ACTIVE_STATES = {"queued", "slicing", "uploading", "printing"}

# Only filenames matching this are accepted — defence against path traversal.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.stl$", re.IGNORECASE)


def _read_sidecar(stl_path: Path) -> dict:
    side = stl_path.with_suffix(stl_path.suffix + ".meta.json")
    if not side.exists():
        return {}
    try:
        data = json.loads(side.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _stl_entry(f: Path) -> dict:
    meta = _read_sidecar(f)
    stat = f.stat()
    return {
        "filename": f.name,
        "stem": f.stem,
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
        "source": meta.get("source", "unknown"),
        "external_url": meta.get("external_url"),
        "thumbnail_url": meta.get("thumbnail_url"),
    }


@router.get("/stls")
async def list_stls() -> JSONResponse:
    """List every .stl in the shared pool, newest first."""
    if not STL_DIR.exists():
        return JSONResponse({"stls": []})
    stls = sorted(
        [_stl_entry(f) for f in STL_DIR.iterdir() if f.is_file() and f.suffix.lower() == ".stl"],
        key=lambda x: x["modified_at"],
        reverse=True,
    )
    return JSONResponse({"stls": stls})


@router.delete("/stls/{filename}")
async def delete_stl(filename: str) -> JSONResponse:
    """Delete an STL from the pool. Refuses if a queued/active job references it."""
    if not _SAFE_NAME.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    stl_path = (STL_DIR / filename).resolve()
    if STL_DIR.resolve() not in stl_path.parents:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not stl_path.exists():
        raise HTTPException(status_code=404, detail="STL not found")

    for job in print_queue.get_jobs():
        if job.get("state") in _ACTIVE_STATES and Path(job.get("stl_path", "")).name == filename:
            raise HTTPException(
                status_code=409,
                detail=f"STL in use by job '{job.get('name')}' ({job.get('state')})",
            )

    stl_path.unlink()
    side = stl_path.with_suffix(stl_path.suffix + ".meta.json")
    if side.exists():
        side.unlink()
    log.info("Deleted STL: %s", filename)
    return JSONResponse({"deleted": filename})


# ── Meshy retrieval jobs (Phase 11 item 3) ───────────────────────────────────

@router.get("/meshy/jobs")
async def list_meshy_jobs() -> JSONResponse:
    """Return Meshy retrieval jobs split into active and recent history."""
    jobs = meshy_jobs.get_jobs()
    active = [j for j in jobs if j["state"] not in ("done", "failed", "cancelled")]
    history = [j for j in jobs if j["state"] in ("done", "failed", "cancelled")]
    return JSONResponse({"active": active, "history": history[-20:]})


@router.delete("/meshy/jobs/{job_id}")
async def cancel_meshy_job(job_id: str) -> JSONResponse:
    """Cancel a pending Meshy job. Already-completed jobs cannot be cancelled."""
    ok = await meshy_jobs.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found or already finished")
    return JSONResponse({"cancelled": job_id})


# ── Thingiverse (Phase 11 item 4) ─────────────────────────────────────────────

class ThingiverseImportBody(BaseModel):
    thing_id: int = Field(..., ge=1)
    file_id: int = Field(..., ge=1)
    # Hints from the client so the saved STL has a recognisable name and the
    # sidecar can link back to the Thing without an extra round-trip.
    thing_name: str = Field("", max_length=120)
    file_name: str = Field("", max_length=120)
    thing_url: str = Field("", max_length=500)
    creator: str = Field("", max_length=80)
    thumbnail_url: str = Field("", max_length=500)


def _require_thingiverse() -> None:
    if not thingiverse.is_configured():
        raise HTTPException(
            status_code=503,
            detail="THINGIVERSE_TOKEN not set — add one in Settings → External APIs",
        )


@router.get("/thingiverse/search")
async def thingiverse_search(
    q: str = Query(..., min_length=1, max_length=120),
    page: int = Query(1, ge=1, le=50),
    per_page: int = Query(20, ge=1, le=40),
) -> JSONResponse:
    _require_thingiverse()
    try:
        result = await thingiverse.search(q, page=page, per_page=per_page)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Thingiverse: {e}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Thingiverse unreachable: {e}")
    return JSONResponse(result)


@router.get("/thingiverse/things/{thing_id}/files")
async def thingiverse_files(thing_id: int) -> JSONResponse:
    _require_thingiverse()
    try:
        files = await thingiverse.get_files(thing_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Thingiverse: {e}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Thingiverse unreachable: {e}")
    return JSONResponse({"files": files})


@router.post("/thingiverse/import")
async def thingiverse_import(body: ThingiverseImportBody) -> JSONResponse:
    """Download a Thingiverse STL into scan_data/stls/ with a Thingiverse sidecar."""
    _require_thingiverse()

    try:
        data, server_filename = await thingiverse.download_file(body.file_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Thingiverse: {e}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Thingiverse unreachable: {e}")

    # Pick a recognisable stem: prefer the client-supplied file name, then the
    # server-provided one, then a generic fallback. Always sanitise and append
    # an 8-hex suffix so re-imports don't collide.
    raw_name = body.file_name or server_filename or f"thing_{body.thing_id}.stl"
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", Path(raw_name).stem)[:40] or f"thing_{body.thing_id}"
    filename = f"{stem}_{uuid.uuid4().hex[:8]}.stl"

    STL_DIR.mkdir(parents=True, exist_ok=True)
    stl_path = STL_DIR / filename
    stl_path.write_bytes(data)

    sidecar = stl_path.with_suffix(stl_path.suffix + ".meta.json")
    sidecar.write_text(json.dumps({
        "source": "thingiverse",
        "external_url": body.thing_url or f"https://www.thingiverse.com/thing:{body.thing_id}",
        "thumbnail_url": body.thumbnail_url or None,
        "thing_id": body.thing_id,
        "file_id": body.file_id,
        "thing_name": body.thing_name,
        "creator": body.creator,
        "source_filename": raw_name,
    }, indent=2))

    log.info(
        "Thingiverse import: thing=%s file=%s → %s (%d bytes)",
        body.thing_id, body.file_id, filename, len(data),
    )
    return JSONResponse({
        "filename": filename,
        "size_bytes": len(data),
        "source": "thingiverse",
    }, status_code=201)
