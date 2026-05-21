"""
Camera management — OpenCV device lifecycle, MJPEG streaming.
"""
import asyncio
import os
import threading

import cv2

from core.logger import get_logger

log = get_logger(__name__)

CAMERA_DEVICE = int(os.getenv("CAMERA_DEVICE") or "0")
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
JPEG_QUALITY = 85
STREAM_FPS = 15


class CameraManager:
    """Manages a single OpenCV camera device."""

    def __init__(self, device_index: int = CAMERA_DEVICE):
        self.device_index = device_index
        self._cap = None
        self._lock = threading.Lock()

    def open(self) -> bool:
        with self._lock:
            if self._cap and self._cap.isOpened():
                return True
            cap = cv2.VideoCapture(self.device_index)
            if not cap.isOpened():
                log.error("Failed to open camera /dev/video%d", self.device_index)
                return False
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            self._cap = cap
            log.info("Camera opened — /dev/video%d %dx%d", self.device_index, FRAME_WIDTH, FRAME_HEIGHT)
            return True

    def close(self) -> None:
        with self._lock:
            if self._cap:
                self._cap.release()
                self._cap = None
                log.info("Camera closed")

    def capture_frame(self):
        """Returns (success: bool, frame: np.ndarray)."""
        with self._lock:
            if not self._cap or not self._cap.isOpened():
                return False, None
            return self._cap.read()

    def is_available(self) -> bool:
        """Quick non-blocking check — does the device node exist?"""
        return os.path.exists(f"/dev/video{self.device_index}")

    async def mjpeg_stream(self):
        """Async generator yielding MJPEG multipart frames as bytes."""
        loop = asyncio.get_event_loop()
        delay = 1.0 / STREAM_FPS
        opened = await loop.run_in_executor(None, self.open)
        if not opened:
            return
        while True:
            ret, frame = await loop.run_in_executor(None, self.capture_frame)
            if not ret or frame is None:
                await asyncio.sleep(0.1)
                continue
            _, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buf.tobytes()
                + b"\r\n"
            )
            await asyncio.sleep(delay)


camera = CameraManager()
