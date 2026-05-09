"""
3D generation routes — OpenSCAD compilation and Meshy proxying.
Bridges local OrcaSlicer/OpenSCAD with the jarvis-api Cloudflare worker.
Implemented in Phase 4F / Phase 5.

POST /api/generate/openscad   — compile OpenSCAD code → STL → R2
POST /api/generate/case       — AI-generate OpenSCAD case from object dims
GET  /api/generate/meshy/{id} — poll Meshy task status (proxy to jarvis-api)
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/openscad")
async def compile_openscad() -> JSONResponse:
    raise NotImplementedError("Phase 5")


@router.post("/case")
async def generate_case() -> JSONResponse:
    raise NotImplementedError("Phase 4F")


@router.get("/meshy/{task_id}")
async def meshy_status(task_id: str) -> JSONResponse:
    raise NotImplementedError("Phase 4F")
