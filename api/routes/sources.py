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

Per-file sidecar: an STL named `foo.stl` may have `foo.stl.meta.json` next to
it with shape `{"source": "<id>", "external_url": "...", ...}`. Import sources
write the sidecar at download time; legacy files have no sidecar and surface
as `source: "unknown"`.
"""
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

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
