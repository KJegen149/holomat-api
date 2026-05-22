import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Callable, Optional

# Broadcast callable + running event loop — wired by main.py's lifespan via
# set_broadcast(), which runs inside the loop so the loop can be captured.
_broadcast: Optional[Callable] = None
_loop: Optional[asyncio.AbstractEventLoop] = None


def set_broadcast(fn: Callable) -> None:
    global _broadcast, _loop
    _broadcast = fn
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = None


class _WebSocketHandler(logging.Handler):
    """Forwards log records to all connected WebSocket clients.

    emit() may be called from any thread (the HA bridge, the print-queue
    worker and the voice-bridge daemon all log), so the broadcast is
    marshalled onto the captured event loop with call_soon_threadsafe.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if _broadcast is None or _loop is None:
            return
        payload = {
            "type": "log",
            "level": record.levelname,
            "name": record.name,
            "message": self.format(record),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(_broadcast(payload))
            )
        except RuntimeError:
            pass  # event loop already closed (shutdown)


def setup_logging() -> None:
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)-28s %(message)s",
        datefmt="%H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # WebSocket broadcast handler — the UI receives ts + level as structured
    # fields and renders them itself, so the broadcast message carries only the
    # logger name + text (using `fmt` here would double the ts/level in the UI).
    wsh = _WebSocketHandler()
    wsh.setFormatter(logging.Formatter("%(name)-28s %(message)s"))
    root.addHandler(wsh)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
