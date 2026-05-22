"""
Object scanning routes.

POST   /api/scan/background        — capture empty-mat background frame
GET    /api/scan/background/status — background capture status
POST   /api/scan/capture           — capture frame with object, run full pipeline
GET    /api/scan/library           — list saved objects (max 50, FIFO)
GET    /api/scan/library/{id}      — get single object record
DELETE /api/scan/library/{id}      — remove object (unless pinned)
PATCH  /api/scan/library/{id}      — update object (pin/unpin, edit dims/notes)
POST   /api/scan/generate-case     — generate OpenSCAD case for a library object
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.logger import get_logger
import core.scanner as scanner

log = get_logger(__name__)
router = APIRouter()


# ── Request models ──────────────────────────────────────────────────────────

class PatchObjectBody(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    height_mm: Optional[float] = Field(None, ge=0)
    pinned: Optional[bool] = None
    notes: Optional[str] = None


class GenerateCaseBody(BaseModel):
    object_id: str
    padding_mm: float = Field(2.0, ge=0, le=20)
    wall_mm: float = Field(2.0, ge=1, le=10)


# ── Background ──────────────────────────────────────────────────────────────

@router.post("/background")
async def capture_background() -> JSONResponse:
    try:
        result = await scanner.capture_background()
        return JSONResponse(result)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/background/status")
async def background_status() -> JSONResponse:
    captured_at = scanner.background_captured_at()
    return JSONResponse({
        "captured": captured_at is not None,
        "captured_at": captured_at,
    })


# ── Scan ────────────────────────────────────────────────────────────────────

@router.post("/capture")
async def scan_object() -> JSONResponse:
    try:
        result = await scanner.scan_object()
        return JSONResponse(result)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Library ─────────────────────────────────────────────────────────────────

@router.get("/library")
async def list_objects() -> JSONResponse:
    lib = scanner.get_library()
    # Strip thumbnail from list view to keep payload small
    slim = [
        {k: v for k, v in entry.items() if k != "thumbnail_b64"}
        for entry in lib
    ]
    return JSONResponse({"items": slim, "count": len(slim)})


@router.get("/library/{object_id}")
async def get_object(object_id: str) -> JSONResponse:
    entry = scanner.get_object(object_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return JSONResponse(entry)


@router.delete("/library/{object_id}")
async def delete_object(object_id: str) -> JSONResponse:
    try:
        found = scanner.delete_object(object_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not found:
        raise HTTPException(status_code=404, detail="Object not found")
    return JSONResponse({"status": "deleted", "id": object_id})


@router.patch("/library/{object_id}")
async def update_object(object_id: str, body: PatchObjectBody) -> JSONResponse:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    entry = scanner.update_object(object_id, updates)
    if entry is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return JSONResponse(entry)


# ── Generate case ───────────────────────────────────────────────────────────

@router.post("/generate-case")
async def generate_case_for_object(body: GenerateCaseBody) -> JSONResponse:
    entry = scanner.get_object(body.object_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Object not found in library")

    height_mm = entry.get("height_mm")
    if height_mm is None:
        height_mm = 20.0  # fallback when height was never measured

    from api.routes.generate import _generate_case_openscad
    try:
        code = await _generate_case_openscad(
            name=entry.get("name", "Object"),
            width_mm=entry.get("width_mm", 0.0),
            depth_mm=entry.get("depth_mm", 0.0),
            height_mm=height_mm,
            padding_mm=body.padding_mm,
            wall_mm=body.wall_mm,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({
        "object_id": body.object_id,
        "name": entry.get("name"),
        "code": code,
    })
