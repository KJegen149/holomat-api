"""
Object scanning pipeline.

Steps:
  1. Capture + undistort frame using calibration camera matrix
  2. Apply homography → perspective-corrected birds-eye view
  3. Background subtraction → isolate object contour
  4. Compute bounding box in mm using pixel→mm ratio from calibration
  5. Send to GPT-4o Vision for object identification
  6. Return: {name, brand, model, category, confidence, width_mm, depth_mm}

Height estimation requires user input (single camera limitation).
Object library is capped at 50 entries (FIFO, user can pin entries).

Implemented in Phase 4.
"""
from core.logger import get_logger

log = get_logger(__name__)

OBJECT_LIBRARY_MAX = 50


async def scan_object(background_frame=None) -> dict:
    """
    Full scan pipeline. Returns identified object with dimensions.
    Raises NotImplementedError until Phase 4.
    """
    raise NotImplementedError("Phase 4")


async def identify_image(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    """
    Send image to GPT-4o Vision. Returns {name, brand, model, category, confidence}.
    Implemented in Phase 4.
    """
    raise NotImplementedError("Phase 4")


def estimate_dimensions(contour, pixels_per_mm: float) -> dict:
    """
    Given an OpenCV contour and the calibration px/mm ratio,
    return {width_mm, depth_mm, area_mm2}.
    Implemented in Phase 4.
    """
    raise NotImplementedError("Phase 4")
