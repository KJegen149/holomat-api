"""
Object scanning pipeline.

Steps:
  1. Capture frame from camera, undistort using calibration camera matrix
  2. Background subtraction (absdiff vs saved background) → binary mask
  3. Morphological cleanup → largest contour
  4. Transform contour through homography → mm-space bounding box
  5. Send undistorted frame to Gemini Vision for object identification
  6. Return: {name, brand, model, category, confidence, width_mm, depth_mm, area_mm2}

Height estimation requires user input (single camera limitation).
Object library is capped at 50 entries (FIFO, user can pin entries).
"""
import asyncio
import base64
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from core.logger import get_logger

log = get_logger(__name__)

SCAN_DIR = Path(__file__).parent.parent / "scan_data"
LIBRARY_FILE = SCAN_DIR / "library.json"
BACKGROUND_FILE = SCAN_DIR / "background.npy"
OBJECT_LIBRARY_MAX = 50

_DIFF_THRESHOLD = int(os.getenv("SCAN_DIFF_THRESHOLD", "30"))
_MIN_CONTOUR_AREA_PX = int(os.getenv("SCAN_MIN_CONTOUR_AREA", "500"))


def _ensure_dir() -> None:
    SCAN_DIR.mkdir(parents=True, exist_ok=True)


# ── Library persistence ─────────────────────────────────────────────────────

def _load_library() -> list[dict]:
    if not LIBRARY_FILE.exists():
        return []
    try:
        return json.loads(LIBRARY_FILE.read_text())
    except Exception as e:
        log.error("Failed to load object library: %s", e)
        return []


def _save_library(lib: list[dict]) -> None:
    _ensure_dir()
    LIBRARY_FILE.write_text(json.dumps(lib, indent=2))


def _add_to_library(entry: dict) -> None:
    lib = _load_library()
    lib.append(entry)
    if len(lib) > OBJECT_LIBRARY_MAX:
        unpinned = [i for i, e in enumerate(lib) if not e.get("pinned", False)]
        if unpinned:
            lib.pop(unpinned[0])
            log.info("Library full — evicted oldest unpinned entry")
    _save_library(lib)


# ── Background management ───────────────────────────────────────────────────

def load_background() -> Optional[np.ndarray]:
    if not BACKGROUND_FILE.exists():
        return None
    try:
        return np.load(str(BACKGROUND_FILE))
    except Exception as e:
        log.error("Failed to load background frame: %s", e)
        return None


def background_captured_at() -> Optional[str]:
    if not BACKGROUND_FILE.exists():
        return None
    mtime = BACKGROUND_FILE.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


async def capture_background() -> dict:
    """Capture and save the empty-mat background frame."""
    from core.calibration import load as load_calibration
    from core.camera import camera

    cal = load_calibration()
    if cal is None:
        raise RuntimeError("Valid calibration required before capturing background")

    cam_matrix = np.array(cal["camera_matrix"], dtype=np.float64)
    dist_coeffs = np.array(cal["dist_coeffs"], dtype=np.float64)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, camera.open)
    ok, frame = await loop.run_in_executor(None, camera.capture_frame)
    if not ok or frame is None:
        raise RuntimeError("Camera not available")

    undistorted = cv2.undistort(frame, cam_matrix, dist_coeffs)
    _ensure_dir()
    np.save(str(BACKGROUND_FILE), undistorted)
    ts = datetime.now(timezone.utc).isoformat()
    log.info("Background frame captured and saved")
    return {"status": "ok", "captured_at": ts}


# ── Main scan pipeline ──────────────────────────────────────────────────────

async def scan_object(background_frame: Optional[np.ndarray] = None) -> dict:
    """Full scan pipeline. Returns identified object with dimensions."""
    from core.calibration import load as load_calibration
    from core.camera import camera

    cal = load_calibration()
    if cal is None:
        raise RuntimeError("Valid calibration required before scanning")

    cam_matrix = np.array(cal["camera_matrix"], dtype=np.float64)
    dist_coeffs = np.array(cal["dist_coeffs"], dtype=np.float64)
    homography = np.array(cal["homography"], dtype=np.float64)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, camera.open)
    ok, frame = await loop.run_in_executor(None, camera.capture_frame)
    if not ok or frame is None:
        raise RuntimeError("Camera not available")

    undistorted = cv2.undistort(frame, cam_matrix, dist_coeffs)

    bg = background_frame if background_frame is not None else load_background()
    if bg is None:
        raise RuntimeError(
            "Background frame required — capture background with an empty mat first"
        )

    # Background subtraction
    diff = cv2.absdiff(undistorted, bg)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, _DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Morphological cleanup — close small holes, remove speckle
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError(
            "No object detected — place object on mat and ensure background was captured with empty mat"
        )

    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < _MIN_CONTOUR_AREA_PX:
        raise RuntimeError(
            "Object footprint too small — move camera closer or check lighting"
        )

    dims = estimate_dimensions(contour, homography)

    # Encode full undistorted frame for GPT-4o
    _, jpeg_buf = cv2.imencode(".jpg", undistorted, [cv2.IMWRITE_JPEG_QUALITY, 85])

    identity = await identify_image(jpeg_buf.tobytes())

    # Thumbnail: padded crop of bounding rect
    x, y, w, h = cv2.boundingRect(contour)
    pad = 20
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(undistorted.shape[1], x + w + pad)
    y2 = min(undistorted.shape[0], y + h + pad)
    crop = undistorted[y1:y2, x1:x2]
    _, thumb_buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 75])
    thumb_b64 = base64.b64encode(thumb_buf).decode()

    entry = {
        "id": str(uuid.uuid4()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "pinned": False,
        "thumbnail_b64": thumb_b64,
        "height_mm": None,
        "notes": None,
        **identity,
        **dims,
    }
    _add_to_library(entry)
    log.info(
        "Scan complete — %s (%.0f×%.0f mm, confidence %.2f)",
        identity.get("name", "unknown"),
        dims.get("width_mm", 0),
        dims.get("depth_mm", 0),
        identity.get("confidence", 0),
    )
    return entry


# ── Gemini Vision ───────────────────────────────────────────────────────────

_VISION_PROMPT = (
    "Identify the object on the black mat in this image. "
    "Reply ONLY with a JSON object (no markdown) with exactly these keys: "
    "name (common name string), "
    "brand (brand string or null), "
    "model (model string or null), "
    "category (one of: electronics, tool, toy, food, office, other), "
    "confidence (float 0.0–1.0)."
)


async def identify_image(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    """Send image to Gemini Vision. Returns {name, brand, model, category, confidence}."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.warning("GEMINI_API_KEY not set — skipping Vision identification")
        return {
            "name": "Unknown Object",
            "brand": None,
            "model": None,
            "category": "unknown",
            "confidence": 0.0,
        }

    try:
        import io
        import PIL.Image
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)

        image = PIL.Image.open(io.BytesIO(image_bytes))
        response = await model.generate_content_async([_VISION_PROMPT, image])
        raw = response.text.strip()

        # Strip markdown code fences if the model adds them anyway
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            ).strip()

        result = json.loads(raw)
        return {
            "name": str(result.get("name", "Unknown")),
            "brand": result.get("brand") or None,
            "model": result.get("model") or None,
            "category": str(result.get("category", "other")),
            "confidence": float(result.get("confidence", 0.0)),
        }

    except Exception as e:
        log.error("Gemini Vision identification failed: %s", e)
        return {
            "name": "Unknown Object",
            "brand": None,
            "model": None,
            "category": "unknown",
            "confidence": 0.0,
        }


# ── Dimension estimation ────────────────────────────────────────────────────

def estimate_dimensions(contour: np.ndarray, homography: np.ndarray) -> dict:
    """
    Transform contour points through homography into mm-space,
    then return axis-aligned bounding box dimensions.
    """
    pts = contour.reshape(-1, 1, 2).astype(np.float32)
    mm_pts = cv2.perspectiveTransform(pts, homography).reshape(-1, 2)

    x_min, y_min = mm_pts.min(axis=0)
    x_max, y_max = mm_pts.max(axis=0)

    width_mm = float(x_max - x_min)
    depth_mm = float(y_max - y_min)

    # Area of the contour polygon in mm² (Shoelace via OpenCV)
    area_mm2 = float(
        cv2.contourArea(mm_pts.reshape(-1, 1, 2).astype(np.float32))
    )

    return {
        "width_mm": round(width_mm, 1),
        "depth_mm": round(depth_mm, 1),
        "area_mm2": round(area_mm2, 1),
    }


# ── Library public API ──────────────────────────────────────────────────────

def get_library() -> list[dict]:
    return _load_library()


def get_object(object_id: str) -> Optional[dict]:
    return next((e for e in _load_library() if e["id"] == object_id), None)


def delete_object(object_id: str) -> bool:
    lib = _load_library()
    entry = next((e for e in lib if e["id"] == object_id), None)
    if entry is None:
        return False
    if entry.get("pinned", False):
        raise ValueError("Cannot delete a pinned object — unpin it first")
    lib = [e for e in lib if e["id"] != object_id]
    _save_library(lib)
    return True


_PATCH_ALLOWED = {"pinned", "name", "brand", "model", "category", "height_mm", "notes"}


def update_object(object_id: str, updates: dict) -> Optional[dict]:
    lib = _load_library()
    for i, entry in enumerate(lib):
        if entry["id"] == object_id:
            for k, v in updates.items():
                if k in _PATCH_ALLOWED:
                    lib[i][k] = v
            _save_library(lib)
            return lib[i]
    return None


def add_manual_object(data: dict) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "pinned": False,
        "thumbnail_b64": None,
        "name": str(data.get("name", "Manual Entry")),
        "brand": data.get("brand"),
        "model": data.get("model"),
        "category": str(data.get("category", "other")),
        "confidence": 1.0,
        "width_mm": float(data.get("width_mm", 0)),
        "depth_mm": float(data.get("depth_mm", 0)),
        "area_mm2": 0.0,
        "height_mm": data.get("height_mm"),
        "notes": data.get("notes"),
    }
    _add_to_library(entry)
    return entry
