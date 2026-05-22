"""
Print pipeline routes — Phase 7.

GET    /api/print/status            — live Bambu P1S state
GET    /api/print/stls              — list compiled STL files available to queue
GET    /api/print/queue             — list all print jobs
POST   /api/print/queue             — add STL to print queue
DELETE /api/print/queue/{job_id}    — cancel queued job
GET    /api/print/profiles          — list print profiles (built-in + custom)
POST   /api/print/profiles          — create custom print profile
DELETE /api/print/profiles/{id}     — delete custom profile
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.print_queue import print_queue
from core.printer import get_status, is_configured
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()

STL_DIR = Path("scan_data/stls")


# ── Request models ────────────────────────────────────────────────────────────

class QueueJobBody(BaseModel):
    stl_filename: str = Field(..., description="Filename inside scan_data/stls/")
    profile_id: str = Field("standard", description="Profile id (draft/standard/fine or custom UUID)")
    name: str = Field("", description="Human-readable job name; defaults to filename stem")


class CreateProfileBody(BaseModel):
    name: str
    layer_height: float = Field(0.20, ge=0.05, le=0.35)
    infill_percent: int = Field(15, ge=5, le=100)
    supports: str = Field("none", pattern="^(none|normal|tree)$")


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def printer_status() -> JSONResponse:
    """Live Bambu P1S status (temperature, progress, state)."""
    result = await get_status()
    return JSONResponse(result)


# ── STL listing ───────────────────────────────────────────────────────────────

@router.get("/stls")
async def list_stls() -> JSONResponse:
    """List .stl files in scan_data/stls/ available for queuing.

    Matches any case (.stl / .STL) so files dropped via the HolomatSTL
    share are picked up alongside OpenSCAD-compiled cases.
    """
    if not STL_DIR.exists():
        return JSONResponse({"stls": []})
    stls = sorted(
        [
            {
                "filename": f.name,
                "stem": f.stem,
                "size_bytes": f.stat().st_size,
                "modified_at": f.stat().st_mtime,
            }
            for f in STL_DIR.iterdir()
            if f.is_file() and f.suffix.lower() == ".stl"
        ],
        key=lambda x: x["modified_at"],
        reverse=True,
    )
    return JSONResponse({"stls": stls})


# ── Queue ─────────────────────────────────────────────────────────────────────

@router.get("/queue")
async def list_queue() -> JSONResponse:
    """List all print jobs (all states)."""
    jobs = print_queue.get_jobs()
    active = [j for j in jobs if j["state"] not in ("done", "failed", "cancelled")]
    history = [j for j in jobs if j["state"] in ("done", "failed", "cancelled")]
    return JSONResponse({"active": active, "history": history[-20:]})


@router.post("/queue")
async def queue_job(body: QueueJobBody) -> JSONResponse:
    """Add an STL file to the print queue."""
    stl_path = STL_DIR / body.stl_filename
    if not stl_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": f"STL not found: {body.stl_filename}"},
        )

    profile = print_queue.get_profile(body.profile_id)
    if profile is None:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown profile: {body.profile_id}"},
        )

    name = body.name.strip() or stl_path.stem
    job = await print_queue.add_job(
        name=name,
        stl_path=str(stl_path.resolve()),
        profile_id=body.profile_id,
    )
    return JSONResponse(status_code=201, content=job)


@router.delete("/queue/{job_id}")
async def cancel_job(job_id: str) -> JSONResponse:
    """Cancel a queued job. Cannot cancel jobs that are already slicing/printing."""
    ok = await print_queue.cancel_job(job_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"error": "Job not found or not in queued state"},
        )
    return JSONResponse({"cancelled": job_id})


# ── Profiles ──────────────────────────────────────────────────────────────────

@router.get("/profiles")
async def list_profiles() -> JSONResponse:
    """List all print profiles (built-in + custom)."""
    return JSONResponse({"profiles": print_queue.get_all_profiles()})


@router.post("/profiles")
async def create_profile(body: CreateProfileBody) -> JSONResponse:
    """Create a custom print profile."""
    profile = print_queue.add_profile(
        name=body.name,
        layer_height=body.layer_height,
        infill_percent=body.infill_percent,
        supports=body.supports,
    )
    return JSONResponse(status_code=201, content=profile)


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> JSONResponse:
    """Delete a custom print profile. Built-in profiles cannot be deleted."""
    # Guard: built-in profiles
    for p in print_queue.get_all_profiles():
        if p["id"] == profile_id and p.get("is_builtin"):
            return JSONResponse(
                status_code=400,
                content={"error": "Built-in profiles cannot be deleted"},
            )
    ok = print_queue.delete_profile(profile_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Profile not found"})
    return JSONResponse({"deleted": profile_id})
