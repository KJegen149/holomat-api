"""
Object scanning routes. Implemented in Phase 4.

POST /api/scan/background   — capture empty-mat background frame
POST /api/scan/capture      — capture frame with object, run full pipeline
GET  /api/scan/library      — list saved objects (max 50, FIFO)
GET  /api/scan/library/{id} — get single object record
POST /api/scan/library      — manually add object by dimensions
DELETE /api/scan/library/{id} — remove object (unless pinned)
PATCH /api/scan/library/{id}  — update object (pin/unpin, edit dims)
POST /api/scan/generate-case  — generate case/accessory for object
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/background")
async def capture_background() -> JSONResponse:
    raise NotImplementedError("Phase 4")


@router.post("/capture")
async def scan_object() -> JSONResponse:
    raise NotImplementedError("Phase 4")


@router.get("/library")
async def list_objects() -> JSONResponse:
    raise NotImplementedError("Phase 4")


@router.get("/library/{object_id}")
async def get_object(object_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 4")


@router.post("/library")
async def add_object() -> JSONResponse:
    raise NotImplementedError("Phase 4")


@router.delete("/library/{object_id}")
async def delete_object(object_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 4")


@router.patch("/library/{object_id}")
async def update_object(object_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 4")


@router.post("/generate-case")
async def generate_case() -> JSONResponse:
    raise NotImplementedError("Phase 4F")
