"""
ChArUco calibration engine.

Calibration data saved to calibration_data/current.json and contains:
  - camera_matrix (3x3)
  - dist_coeffs (1x5)
  - homography (3x3)  — maps undistorted pixels → mat coordinates in mm
  - rmse            — reprojection error in pixels
  - captured_at     — ISO timestamp
  - point_count     — number of accepted captures

Minimum 12 captures required. RMSE must be < 1.0 px.
System blocks boot into normal mode until valid calibration exists.

Implemented in Phase 1.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger(__name__)

CALIBRATION_FILE = Path(__file__).parent.parent / "calibration_data" / "current.json"
MIN_CAPTURES = 12
MAX_RMSE = 1.0
MAX_AGE_DAYS = 30


def load() -> Optional[dict]:
    """Return calibration data dict if valid calibration exists, else None."""
    if not CALIBRATION_FILE.exists():
        return None
    try:
        data = json.loads(CALIBRATION_FILE.read_text())
        captured_at = datetime.fromisoformat(data["captured_at"])
        age = (datetime.now(timezone.utc) - captured_at).days
        if age >= MAX_AGE_DAYS:
            log.warning("Calibration is %d days old — recalibration required", age)
            return None
        return data
    except Exception as e:
        log.error("Failed to load calibration: %s", e)
        return None


def is_valid() -> bool:
    return load() is not None


def invalidate() -> None:
    if CALIBRATION_FILE.exists():
        CALIBRATION_FILE.unlink()
        log.info("Calibration data removed — recalibration required")


class CalibrationSession:
    """
    Manages an active calibration session: capturing frames,
    detecting ChArUco corners, and computing the final calibration.
    Implemented in Phase 1.
    """

    def __init__(self):
        self.captures = []

    def capture(self, frame) -> dict:
        """Detect corners in frame and add to capture set if valid."""
        raise NotImplementedError("Phase 1")

    def compute(self) -> dict:
        """Run cv2.calibrateCamera() and save result."""
        raise NotImplementedError("Phase 1")

    @property
    def capture_count(self) -> int:
        return len(self.captures)

    @property
    def ready(self) -> bool:
        return self.capture_count >= MIN_CAPTURES
