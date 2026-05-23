import os
import platform
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core import calibration as cal
from core.camera import camera
from core.printer import is_configured as printer_configured
from core.slicer import orca_available, openscad_available
from core.smb_watcher import watcher as smb_watcher
from core.ha_bridge import ha_bridge
from core.scanner import background_captured_at, get_library
from api.websocket import manager as ws_manager
from core.logger import get_logger
from core.version import VERSION

log = get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    calib_data = cal.load()
    return JSONResponse({
        "status": "ok",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "calibration": {
            "valid": calib_data is not None,
            "captured_at": calib_data.get("captured_at") if calib_data else None,
            "point_count": calib_data.get("point_count") if calib_data else 0,
            "rmse": calib_data.get("rmse") if calib_data else None,
        },
        "hardware": {
            "camera_detected": camera.is_available(),
            "printer_configured": printer_configured(),
            "orca_slicer": orca_available(),
            "openscad": openscad_available(),
        },
        "services": {
            "smb_watcher":    smb_watcher.running,
            "ws_clients":     ws_manager.connection_count,
            "cf_api_url":     os.getenv("CF_API_URL", ""),
            "cf_api_key_set": bool(os.getenv("CF_API_KEY", "")),
            "ha_bridge":      ha_bridge.running,
            "ha_url":         os.getenv("HA_URL", ""),
        },
        "scanner": {
            "background_captured": background_captured_at() is not None,
            "library_count":       len(get_library()),
        },
    })


@router.get("/status")
async def status() -> JSONResponse:
    """Lightweight liveness probe — calibration gate check."""
    return JSONResponse({
        "ready": cal.is_valid(),
        "calibration_required": not cal.is_valid(),
        "version": VERSION,
    })
