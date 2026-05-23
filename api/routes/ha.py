"""Home Assistant bridge status and manual push endpoints."""
import os
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.ha_bridge import ha_bridge
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.get("/status")
async def ha_status() -> JSONResponse:
    return JSONResponse({
        "configured": ha_bridge.is_configured(),
        "running":    ha_bridge.running,
        "broker": {
            "host": os.getenv("HA_MQTT_HOST", ""),
            "port": int(os.getenv("HA_MQTT_PORT") or "1883"),
        },
        "ha_url":    os.getenv("HA_URL", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@router.post("/push")
async def ha_push() -> JSONResponse:
    """Manually trigger an immediate state push to HA."""
    if not ha_bridge.running:
        return JSONResponse(
            status_code=503,
            content={"error": "ha_bridge_offline", "detail": "HA bridge is not running"},
        )
    ha_bridge.push()
    log.info("Manual HA state push triggered")
    return JSONResponse({"pushed": True, "timestamp": datetime.now(timezone.utc).isoformat()})
