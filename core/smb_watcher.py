"""
Samba share file watcher.

Monitors smb_share/ directory for new image files dropped from any
device on the network (via \\KJLC-AI-01\HolomatGallery).

On new file:
  1. Convert HEIC → JPEG if needed (pillow-heif)
  2. Upload to Cloudflare R2 under gallery/ prefix via jarvis-api
  3. Broadcast WebSocket event: {type: "gallery_new", item: {...}}
  4. Remove the source file from smb_share/
"""
import asyncio
import io
import os
import threading
import time
from pathlib import Path
from typing import Optional

import httpx
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from core.logger import get_logger

log = get_logger(__name__)

WATCH_DIR = Path(__file__).parent.parent / "smb_share"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif"}

_CF_API_URL = lambda: os.getenv("CF_API_URL", "")
_CF_API_KEY = lambda: os.getenv("CF_API_KEY", "")

_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _wait_stable(path: Path, interval: float = 0.4, attempts: int = 12) -> bool:
    """Return True once the file size stops changing (write complete)."""
    last_size = -1
    for _ in range(attempts):
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == last_size and size > 0:
            return True
        last_size = size
        time.sleep(interval)
    return last_size > 0


def _read_image(path: Path) -> tuple[bytes, str, str]:
    """
    Read image, converting HEIC/HEIF to JPEG first if needed.
    Returns (data_bytes, content_type, output_filename).
    """
    ext = path.suffix.lower()
    if ext in {".heic", ".heif"}:
        import pillow_heif
        from PIL import Image as PilImage

        pillow_heif.register_heif_opener()
        img = PilImage.open(path)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        return buf.getvalue(), "image/jpeg", path.stem + ".jpg"

    return path.read_bytes(), _CONTENT_TYPES.get(ext, "image/jpeg"), path.name


def _upload(data: bytes, content_type: str, filename: str) -> Optional[dict]:
    """Upload image bytes to jarvis-api /api/gallery. Returns item dict or None."""
    api_url = _CF_API_URL()
    api_key = _CF_API_KEY()
    if not api_url or not api_key:
        log.warning("CF_API_URL/CF_API_KEY not set — gallery upload skipped")
        return None
    try:
        r = httpx.post(
            f"{api_url}/api/gallery",
            content=data,
            headers={
                "X-API-Key": api_key,
                "Content-Type": content_type,
                "X-File-Name": filename,
                "X-Source": "smb",
            },
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.error("Gallery upload failed: %s", exc)
        return None


class _EventHandler(FileSystemEventHandler):
    """Handles watchdog events from the SMB share directory."""

    def __init__(self, loop: asyncio.AbstractEventLoop, broadcast):
        super().__init__()
        self._loop = loop
        self._broadcast = broadcast
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def _enqueue(self, src_path: str) -> None:
        with self._lock:
            if src_path in self._seen:
                return
            self._seen.add(src_path)
        t = threading.Thread(target=self._process, args=(src_path,), daemon=True)
        t.start()

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._enqueue(event.src_path)

    # inotify fires IN_CLOSE_WRITE as FileClosedEvent on Linux — more reliable
    def on_closed(self, event) -> None:
        if not event.is_directory:
            self._enqueue(event.src_path)

    def _process(self, src_path: str) -> None:
        path = Path(src_path)
        try:
            if not path.exists():
                return  # already ingested by a sibling create/close event
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                return
            if not _wait_stable(path):
                log.warning("File never stabilized, skipping: %s", path.name)
                return

            data, content_type, filename = _read_image(path)
            item = _upload(data, content_type, filename)

            if item:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast({"type": "gallery_new", "item": item}),
                    self._loop,
                )
                log.info("Gallery ingest OK: %s → id=%s", path.name, item.get("id"))
            else:
                log.warning("Gallery upload returned nothing for %s", path.name)

            path.unlink(missing_ok=True)
        except Exception:
            log.exception("Gallery ingest error for %s", path.name)
        finally:
            with self._lock:
                self._seen.discard(src_path)


class GalleryWatcher:
    """watchdog-based directory monitor for the Samba share."""

    def __init__(self):
        self._observer: Optional[Observer] = None
        self._running = False

    def start(self) -> None:
        loop = asyncio.get_running_loop()

        from api.websocket import manager as ws_manager

        WATCH_DIR.mkdir(parents=True, exist_ok=True)
        handler = _EventHandler(loop, ws_manager.broadcast)
        self._observer = Observer()
        self._observer.schedule(handler, str(WATCH_DIR), recursive=False)
        self._observer.start()
        self._running = True
        log.info("SMB gallery watcher started — %s", WATCH_DIR)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._running = False
        log.info("SMB gallery watcher stopped")

    @property
    def running(self) -> bool:
        return self._running


watcher = GalleryWatcher()
