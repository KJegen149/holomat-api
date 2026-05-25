import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.auth import COOKIE_NAME, auth_enabled, verify_session
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()

# WebSocket close code for "your session lapsed, drop to login". The
# useWebSocket hook routes this back to the login screen instead of
# silently reconnecting.
WS_AUTH_FAILED = 4401


class ConnectionManager:
    """Manages all active WebSocket connections and broadcasts events."""

    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        log.info("WebSocket client connected — %d active", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        log.info("WebSocket client disconnected — %d active", len(self._connections))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send JSON payload to all connected clients, pruning dead connections."""
        dead: set[WebSocket] = set()
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._connections -= dead

    @property
    def connection_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    if auth_enabled():
        token = ws.cookies.get(COOKIE_NAME)
        if not token or verify_session(token) is None:
            await ws.close(code=WS_AUTH_FAILED)
            return
    await manager.connect(ws)
    try:
        while True:
            # Keep-alive: accept any client message, echo pings
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        log.warning("WebSocket error: %s", e)
        manager.disconnect(ws)
