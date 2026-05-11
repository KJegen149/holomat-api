"""
Holomat API  v0.7.0
JARVIS Holomat — smart fabrication surface
Runs on KJLC-AI-01 (10.11.12.129), port 8100

Phase structure:
  Phase 0  — bootstrap (this file)
  Phase 1  — calibration engine
  Phase 2  — UI shell (React/Vite, replaces ui/index.html placeholder)
  Phase 3  — Home Assistant embedding (MQTT discovery + HA dashboard iframe)
  Phase 4  — object scanning pipeline
  Phase 5  — OpenSCAD → STL compilation
  Phase 6  — gallery / SMB watcher
  Phase 7  — print queue (Bambu P1S) ← current
  Phase 8  — voice bridge / HA satellite
  Phase 9+ — settings, polish, batch scan
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.logger import get_logger, set_broadcast, setup_logging
from api.websocket import manager as ws_manager, router as ws_router
from api.routes.system import router as system_router
from api.routes.camera import router as camera_router
from api.routes.calibration import router as calibration_router
from api.routes.scan import router as scan_router
from api.routes.print import router as print_router
from api.routes.gallery import router as gallery_router
from api.routes.generate import router as generate_router
from api.routes.ha import router as ha_router

setup_logging()
log = get_logger(__name__)

BASE_DIR = Path(__file__).parent
UI_DIST = BASE_DIR / "ui" / "dist"          # Phase 2+: built React app
UI_PLACEHOLDER = BASE_DIR / "ui" / "index.html"  # Phase 0-1: boot placeholder


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wire logger → WebSocket so all log lines stream to the Console app
    set_broadcast(ws_manager.broadcast)
    log.info("━━━ Holomat v0.7.0 starting — Phase 7 ━━━")

    # HA MQTT bridge (Phase 3)
    try:
        from core.ha_bridge import ha_bridge
        ha_bridge.start()
    except NotImplementedError:
        log.info("HA bridge pending — set HA_MQTT_HOST to enable")
    except Exception as e:
        log.warning("HA bridge failed to start: %s", e)

    # SMB watcher (Phase 6)
    try:
        from core.smb_watcher import watcher
        watcher.start()
    except NotImplementedError:
        log.info("SMB watcher pending (Phase 6)")
    except Exception as e:
        log.warning("SMB watcher failed to start: %s", e)

    # Print queue worker (Phase 7)
    try:
        from core.print_queue import print_queue
        print_queue.set_broadcast(ws_manager.broadcast)
        print_queue.start()
    except Exception as e:
        log.warning("Print queue failed to start: %s", e)

    # Voice bridge (Phase 8)
    try:
        from core.voice_bridge import voice_bridge
        voice_bridge.start()
    except NotImplementedError:
        log.info("Voice bridge pending (Phase 8)")
    except Exception as e:
        log.warning("Voice bridge failed to start: %s", e)

    log.info("Holomat API ready — http://0.0.0.0:8100")
    yield

    log.info("Holomat shutting down")
    try:
        from core.ha_bridge import ha_bridge
        ha_bridge.stop()
    except Exception:
        pass
    try:
        from core.print_queue import print_queue
        print_queue.stop()
    except Exception:
        pass
    for name, obj in [("SMB watcher", "watcher"), ("Voice bridge", "voice_bridge")]:
        try:
            mod = __import__(
                "core.smb_watcher" if "SMB" in name else "core.voice_bridge",
                fromlist=[obj],
            )
            getattr(mod, obj).stop()
        except Exception:
            pass


# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Holomat API",
    version="0.7.0",
    description="JARVIS Holomat — smart fabrication surface",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(ws_router)
app.include_router(system_router,      prefix="/api")
app.include_router(camera_router,      prefix="/api/camera")
app.include_router(calibration_router, prefix="/api/calibration")
app.include_router(scan_router,        prefix="/api/scan")
app.include_router(print_router,       prefix="/api/print")
app.include_router(gallery_router,     prefix="/api/gallery")
app.include_router(generate_router,    prefix="/api/generate")
app.include_router(ha_router,          prefix="/api/ha")


# ── Static UI serving ──────────────────────────────────────────────────────
# Phase 2+: serve the built React/Vite app from ui/dist/
# Phase 0-1: serve the placeholder ui/index.html
if UI_DIST.exists():
    _assets = UI_DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        return FileResponse(str(UI_DIST / "index.html"))

else:
    @app.get("/", include_in_schema=False)
    async def serve_placeholder() -> FileResponse:
        return FileResponse(str(UI_PLACEHOLDER))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def redirect_to_root(full_path: str) -> FileResponse:
        return FileResponse(str(UI_PLACEHOLDER))


# ── Global exception handlers ──────────────────────────────────────────────
@app.exception_handler(NotImplementedError)
async def not_implemented(request: Request, exc: NotImplementedError) -> JSONResponse:
    phase = str(exc) if str(exc) else "a future phase"
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": f"Implemented in {phase}"},
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": str(exc)},
    )
