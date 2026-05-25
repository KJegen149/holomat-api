"""
Holomat API — JARVIS Holomat, a smart fabrication surface.
Runs on KJLC-AI-01, port 8100.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.auth import auth_enabled, bootstrap_if_missing, require_auth
from core.logger import get_logger, set_broadcast, setup_logging
from core.version import VERSION
from api.websocket import manager as ws_manager, router as ws_router
from api.routes.auth import router as auth_router
from api.routes.system import router as system_router
from api.routes.camera import router as camera_router
from api.routes.calibration import router as calibration_router
from api.routes.scan import router as scan_router
from api.routes.print import router as print_router
from api.routes.gallery import router as gallery_router
from api.routes.generate import router as generate_router
from api.routes.sources import router as sources_router
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

    # Auth bootstrap — no-op when HOLOMAT_AUTH_ENABLED=false
    try:
        bootstrap_if_missing()
        if auth_enabled():
            log.info("Auth: ENABLED — session cookie required for /api/*")
        else:
            log.info("Auth: DISABLED (HOLOMAT_AUTH_ENABLED=false) — all routes anonymous")
    except Exception as e:
        log.error("Auth bootstrap failed: %s", e)

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

    # Meshy retrieval worker (Phase 11)
    try:
        from core.meshy_jobs import meshy_jobs
        meshy_jobs.set_broadcast(ws_manager.broadcast)
        meshy_jobs.start()
    except Exception as e:
        log.warning("Meshy retrieval worker failed to start: %s", e)

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
    try:
        from core.meshy_jobs import meshy_jobs
        meshy_jobs.stop()
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

def _allowed_origins() -> list[str]:
    """Comma-separated CORS allow-list. Same-origin SPA requests don't hit
       CORS at all, so an empty list is the safest default — the operator
       only needs to populate this if a cross-origin client (e.g. HA) calls
       the API directly."""
    raw = os.getenv("HOLOMAT_ALLOWED_ORIGINS", "").strip()
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
# Public routers:
#   - /ws                       — auth-checked inside the handler (cookies)
#   - /api/auth/*               — login, logout, /me must be reachable pre-auth
#   - /api/health (in system_router) — login screen polls this for the status pill
#                                       /api/status inside system_router is gated
#                                       individually with Depends(require_auth)
# Everything else is gated at router level by require_auth.
_AUTH_DEP = [Depends(require_auth)]

app.include_router(ws_router)
app.include_router(auth_router,        prefix="/api/auth")
app.include_router(system_router,      prefix="/api")
app.include_router(camera_router,      prefix="/api/camera",      dependencies=_AUTH_DEP)
app.include_router(calibration_router, prefix="/api/calibration", dependencies=_AUTH_DEP)
app.include_router(scan_router,        prefix="/api/scan",        dependencies=_AUTH_DEP)
app.include_router(print_router,       prefix="/api/print",       dependencies=_AUTH_DEP)
app.include_router(gallery_router,     prefix="/api/gallery",     dependencies=_AUTH_DEP)
app.include_router(generate_router,    prefix="/api/generate",    dependencies=_AUTH_DEP)
app.include_router(sources_router,     prefix="/api/sources",     dependencies=_AUTH_DEP)
app.include_router(ha_router,          prefix="/api/ha",          dependencies=_AUTH_DEP)
app.include_router(voice_router,       prefix="/api/voice",       dependencies=_AUTH_DEP)
app.include_router(settings_router,    prefix="/api/settings",    dependencies=_AUTH_DEP)


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


@app.exception_handler(httpx.HTTPError)
async def upstream_error(request: Request, exc: httpx.HTTPError) -> JSONResponse:
    log.warning("Upstream HTTP error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=502,
        content={"error": "upstream_error", "detail": str(exc)},
    )


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": str(exc)},
    )
