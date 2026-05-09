"""
Camera management — OpenCV device lifecycle, MJPEG streaming.
Implemented in Phase 1 (calibration) and Phase 4 (scanning).
"""
from core.logger import get_logger

log = get_logger(__name__)


class CameraManager:
    """Manages a single OpenCV camera device."""

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self._cap = None

    def open(self) -> bool:
        raise NotImplementedError("Phase 1")

    def close(self) -> None:
        raise NotImplementedError("Phase 1")

    def capture_frame(self):
        """Returns (success: bool, frame: np.ndarray)."""
        raise NotImplementedError("Phase 1")

    def is_available(self) -> bool:
        """Quick non-blocking check — does the device node exist?"""
        import os
        return os.path.exists(f"/dev/video{self.device_index}")

    async def mjpeg_stream(self):
        """Async generator yielding MJPEG frames as bytes."""
        raise NotImplementedError("Phase 1")


camera = CameraManager()
