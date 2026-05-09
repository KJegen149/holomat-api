"""
Samba share file watcher.

Monitors smb_share/ directory for new image files dropped from any
device on the network (via \\KJLC-AI-01\HolomatGallery).

On new file:
  1. Convert HEIC → JPEG if needed (pillow-heif)
  2. Upload to Cloudflare R2 under gallery/ prefix via jarvis-api
  3. Insert record into D1 gallery_items table
  4. Broadcast WebSocket event: {type: "gallery_new", item: {...}}

Implemented in Phase 6.
"""
import os
from pathlib import Path

from core.logger import get_logger

log = get_logger(__name__)

WATCH_DIR = Path(__file__).parent.parent / "smb_share"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif"}


class GalleryWatcher:
    """watchdog-based directory monitor for the Samba share."""

    def __init__(self):
        self._observer = None
        self._running = False

    def start(self) -> None:
        """Start the watchdog observer. Implemented in Phase 6."""
        raise NotImplementedError("Phase 6")

    def stop(self) -> None:
        """Stop the watchdog observer. Implemented in Phase 6."""
        if self._observer:
            self._observer.stop()
            self._running = False

    @property
    def running(self) -> bool:
        return self._running


watcher = GalleryWatcher()
