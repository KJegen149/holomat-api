"""
Calibration API routes.

GET  /api/calibration/status   — current calibration state
GET  /api/camera/stream        — MJPEG stream for live preview
POST /api/calibration/capture  — capture frame, detect ChArUco corners
POST /api/calibration/compute  — run calibrateCamera(), save result
DELETE /api/calibration/reset  — invalidate and force recalibration

Full implementation in Phase 1.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core import calibration as cal
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()

_session = None  # Active CalibrationSession, if any


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
    })


@router.post("/capture")
async def capture_frame() -> JSONResponse:
    raise NotImplementedError("Calibration capture implemented in Phase 1")


@router.post("/compute")
async def compute_calibration() -> JSONResponse:
    raise NotImplementedError("Calibration compute implemented in Phase 1")


@router.delete("/reset")
async def reset_calibration() -> JSONResponse:
    cal.invalidate()
    return JSONResponse({"reset": True, "message": "Calibration cleared — recalibration required on next boot"})
