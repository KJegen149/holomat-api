"""
Print pipeline routes. Implemented in Phase 5.

GET  /api/print/status      — live printer state (temp, progress, state)
POST /api/print/queue       — add job to print queue
GET  /api/print/queue       — list queued + active jobs
DELETE /api/print/queue/{id} — cancel queued job
POST /api/print/slice       — slice an STL/GLB and add to queue
GET  /api/print/profiles    — list saved print profiles
POST /api/print/profiles    — create print profile
DELETE /api/print/profiles/{id} — delete print profile
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.printer import get_status
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.get("/status")
async def printer_status() -> JSONResponse:
    """Live Bambu P1S status — operational now (migrated from Phase 2A)."""
    result = await get_status()
    return JSONResponse(result)


@router.post("/queue")
async def queue_job() -> JSONResponse:
    raise NotImplementedError("Phase 5")


@router.get("/queue")
async def list_queue() -> JSONResponse:
    raise NotImplementedError("Phase 5")


@router.delete("/queue/{job_id}")
async def cancel_job(job_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 5")


@router.post("/slice")
async def slice_and_queue() -> JSONResponse:
    raise NotImplementedError("Phase 5")


@router.get("/profiles")
async def list_profiles() -> JSONResponse:
    raise NotImplementedError("Phase 5")


@router.post("/profiles")
async def create_profile() -> JSONResponse:
    raise NotImplementedError("Phase 5")


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 5")
