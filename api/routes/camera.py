"""
Camera routes.

GET  /api/camera/status  — camera availability
GET  /api/camera/stream  — MJPEG live preview (multipart/x-mixed-replace)
"""
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from core.camera import camera
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.get("/status")
async def camera_status() -> JSONResponse:
    return JSONResponse({
        "available": camera.is_available(),
        "device": camera.device_index,
    })


@router.get("/stream")
async def camera_stream():
    """MJPEG live stream for calibration / scanning preview."""
    loop = asyncio.get_event_loop()
    opened = await loop.run_in_executor(None, camera.open)
    if not opened:
        return JSONResponse({"error": "camera_unavailable"}, status_code=503)
    return StreamingResponse(
        camera.mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
