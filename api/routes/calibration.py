"""
Calibration API routes.

GET    /api/calibration/status   — current calibration state + active session info
POST   /api/calibration/capture  — grab frame from camera, detect ChArUco corners
POST   /api/calibration/compute  — run calibrateCamera(), save result
DELETE /api/calibration/reset    — invalidate saved calibration and clear session
"""
import asyncio
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core import calibration as cal
from core.calibration import CalibrationSession
from core.camera import camera
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()

_session: Optional[CalibrationSession] = None


def _get_or_create_session() -> CalibrationSession:
    global _session
    if _session is None:
        _session = CalibrationSession()
        log.info("Calibration session started")
    return _session


@router.get("/status")
async def calibration_status() -> JSONResponse:
    data = cal.load()
    return JSONResponse({
        "valid": data is not None,
        "captured_at": data.get("captured_at") if data else None,
        "point_count": data.get("point_count") if data else 0,
        "rmse": data.get("rmse") if data else None,
        "min_captures_required": cal.MIN_CAPTURES,
        "max_rmse": cal.MAX_RMSE,
        "session_captures": _session.capture_count if _session else 0,
        "session_ready": _session.ready if _session else False,
    })


@router.post("/capture")
async def capture_frame() -> JSONResponse:
    """Grab a frame from the camera and attempt ChArUco corner detection."""
    loop = asyncio.get_running_loop()
    session = _get_or_create_session()

    opened = await loop.run_in_executor(None, camera.open)
    if not opened:
        return JSONResponse({"error": "camera_unavailable"}, status_code=503)

    ret, frame = await loop.run_in_executor(None, camera.capture_frame)
    if not ret or frame is None:
        return JSONResponse({"error": "capture_failed"}, status_code=503)

    result = await loop.run_in_executor(None, session.capture, frame)
    return JSONResponse({
        **result,
        "ready_to_compute": session.ready,
        "min_captures_required": cal.MIN_CAPTURES,
    })


@router.post("/compute")
async def compute_calibration() -> JSONResponse:
    """Run calibrateCamera() on collected captures and persist result."""
    global _session
    session = _session

    if session is None or session.capture_count == 0:
        return JSONResponse(
            {
                "error": "no_captures",
                "detail": "Start a session with POST /api/calibration/capture first",
            },
            status_code=400,
        )

    if not session.ready:
        return JSONResponse(
            {
                "error": "insufficient_captures",
                "detail": (
                    f"Need {cal.MIN_CAPTURES} captures, have {session.capture_count}"
                ),
                "capture_count": session.capture_count,
                "min_captures_required": cal.MIN_CAPTURES,
            },
            status_code=400,
        )

    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(None, session.compute)
    except ValueError as exc:
        return JSONResponse(
            {"error": "calibration_failed", "detail": str(exc)}, status_code=422
        )
    except Exception:
        log.exception("Calibration compute failed")
        return JSONResponse(
            {"error": "calibration_failed", "detail": "Unexpected error — check logs"},
            status_code=500,
        )

    _session = None  # clear session on success
    return JSONResponse(
        {
            "success": True,
            "rmse": data["rmse"],
            "point_count": data["point_count"],
            "captured_at": data["captured_at"],
        }
    )


@router.delete("/reset")
async def reset_calibration() -> JSONResponse:
    global _session
    _session = None
    cal.invalidate()
    return JSONResponse(
        {"reset": True, "message": "Calibration cleared — recalibration required on next boot"}
    )
