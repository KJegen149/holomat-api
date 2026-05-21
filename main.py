"""
Holomat API — JARVIS Holomat, a smart fabrication surface.
Runs on KJLC-AI-01, port 8100.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.logger import get_logger, set_broadcast, setup_logging
from core.version import VERSION
from api.websocket import manager as ws_manager, router as ws_router
from api.routes.system import router as system_router
from api.routes.camera import router as camera_router
from api.routes.calibration import router as calibration_router
from api.routes.scan import router as scan_router
from api.routes.print import router as print_router
from api.routes.gallery import router as gallery_router
from api.routes.generate import router as generate_router
from api.routes.ha import router as ha_router
from api.routes.voice import router as voice_router
from api.routes.settings import router as settings_router

setup_logging()
log = get_logger(__name__)

BASE_DIR = Path(__file__).parent
UI_DIST = BASE_DIR / "ui" / "dist"          # built React app
UI_PLACEHOLDER = BASE_DIR / "ui" / "index.html"  # boot placeholder


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wire logger → WebSocket so all log lines stream to the Console app
    set_broadcast(ws_manager.broadcast)
    log.info("━━━ Holomat v%s starting ━━━", VERSION)

    # HA MQTT bridge
    try:
        from core.ha_bridge import ha_bridge
        ha_bridge.start()
    except NotImplementedError:
        log.info("HA bridge pending — set HA_MQTT_HOST to enable")
    except Exception as e:
        log.warning("HA bridge failed to start: %s", e)

    # SMB watcher
    try:
        from core.smb_watcher import watcher
        watcher.start()
    except NotImplementedError:
        log.info("SMB watcher pending")
    except Exception as e:
        log.warning("SMB watcher failed to start: %s", e)

    # Print queue worker
    try:
        from core.print_queue import print_queue
        print_queue.set_broadcast(ws_manager.broadcast)
        print_queue.start()
    except Exception as e:
        log.warning("Print queue failed to start: %s", e)

    # Voice bridge
    try:
        from core.voice_bridge import voice_bridge
        voice_bridge.set_broadcast(ws_manager.broadcast)
        voice_bridge.start()
    except NotImplementedError:
        log.info("Voice bridge pending — set WYOMING_ENABLED=true to activate")
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
    version=VERSION,
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
app.include_router(voice_router,       prefix="/api/voice")
app.include_router(settings_router,    prefix="/api/settings")


# ── Static UI serving ──────────────────────────────────────────────────────
# serve the built React/Vite app from ui/dist/
# falls back to the placeholder ui/index.html
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
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": str(exc) or "Feature not available"},
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": str(exc)},
    )
