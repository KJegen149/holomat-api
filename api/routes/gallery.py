"""
Gallery routes — SMB share image browser and 3D conversion pipeline.
Implemented in Phase 6.

GET  /api/gallery           — list gallery items (paginated)
GET  /api/gallery/{id}      — single gallery item
DELETE /api/gallery/{id}    — remove from gallery + R2
POST /api/gallery/{id}/generate-3d  — submit to Meshy image-to-3D
POST /api/gallery/{id}/generate-svg — send image to LLM for SVG recreation
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.get("")
async def list_gallery() -> JSONResponse:
    raise NotImplementedError("Phase 6")


@router.get("/{item_id}")
async def get_gallery_item(item_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 6")


@router.delete("/{item_id}")
async def delete_gallery_item(item_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 6")


@router.post("/{item_id}/generate-3d")
async def gallery_to_3d(item_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 6")


@router.post("/{item_id}/generate-svg")
async def gallery_to_svg(item_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 6")
