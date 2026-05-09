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

Board: DICT_4X4_100, 7×5 squares, 40 mm square / 30 mm marker (env-overridable).
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from core.logger import get_logger

log = get_logger(__name__)

CALIBRATION_FILE = Path(__file__).parent.parent / "calibration_data" / "current.json"
MIN_CAPTURES = 12
MAX_RMSE = 1.0
MAX_AGE_DAYS = 30

# ChArUco board geometry — mm, env-overridable
_BOARD_COLS = int(os.getenv("CHARUCO_COLS", "7"))
_BOARD_ROWS = int(os.getenv("CHARUCO_ROWS", "5"))
_SQUARE_MM = float(os.getenv("CHARUCO_SQUARE_MM", "40.0"))
_MARKER_MM = float(os.getenv("CHARUCO_MARKER_MM", "30.0"))
_MIN_CHARUCO_CORNERS = int(os.getenv("CHARUCO_MIN_CORNERS", "6"))


def _make_board():
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
    board = cv2.aruco.CharucoBoard(
        (_BOARD_COLS, _BOARD_ROWS), _SQUARE_MM, _MARKER_MM, dictionary
    )
    return dictionary, board


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
    """

    def __init__(self):
        self._dictionary, self._board = _make_board()
        self._detector = cv2.aruco.CharucoDetector(self._board)
        # Each entry: (charuco_corners, charuco_ids, image_size)
        self._captures: list[tuple] = []

    # ── Public API ─────────────────────────────────────────────────────────

    def capture(self, frame) -> dict:
        """Detect ChArUco corners in frame; add to capture set if sufficient."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        image_size = (gray.shape[1], gray.shape[0])  # (width, height)

        charuco_corners, charuco_ids, _m_corners, _m_ids = (
            self._detector.detectBoard(gray)
        )

        markers_found = len(_m_ids) if _m_ids is not None else 0

        if charuco_ids is None or len(charuco_ids) < _MIN_CHARUCO_CORNERS:
            return {
                "accepted": False,
                "markers_found": markers_found,
                "corners_found": len(charuco_ids) if charuco_ids is not None else 0,
                "capture_count": self.capture_count,
            }

        self._captures.append((charuco_corners, charuco_ids, image_size))
        corners_found = len(charuco_ids)
        log.info(
            "Calibration capture %d accepted — %d ChArUco corners",
            self.capture_count, corners_found,
        )
        return {
            "accepted": True,
            "markers_found": markers_found,
            "corners_found": corners_found,
            "capture_count": self.capture_count,
        }

    def compute(self) -> dict:
        """Run cv2.calibrateCamera() via matchImagePoints and save result."""
        if not self.ready:
            raise ValueError(
                f"Need at least {MIN_CAPTURES} captures, have {self.capture_count}"
            )

        image_size = self._captures[0][2]
        obj_points_all: list[np.ndarray] = []
        img_points_all: list[np.ndarray] = []

        for charuco_corners, charuco_ids, _ in self._captures:
            obj_pts, img_pts = self._board.matchImagePoints(charuco_corners, charuco_ids)
            if obj_pts is not None and len(obj_pts) >= 4:
                obj_points_all.append(obj_pts)
                img_points_all.append(img_pts)

        if len(obj_points_all) < 4:
            raise ValueError("Too few valid captures after corner matching — recapture required")

        rmse, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            obj_points_all, img_points_all, image_size, None, None
        )
        log.info("Camera calibration RMSE = %.4f px", rmse)

        if rmse > MAX_RMSE:
            raise ValueError(
                f"RMSE {rmse:.3f} px exceeds threshold {MAX_RMSE} px — recapture required"
            )

        # Use the last capture to compute pixel→mm homography for the mat plane
        last_corners, last_ids, _ = self._captures[-1]
        homography = self._compute_homography(last_corners, last_ids, camera_matrix, dist_coeffs)

        data = {
            "camera_matrix": camera_matrix.tolist(),
            "dist_coeffs": dist_coeffs.tolist(),
            "homography": homography.tolist(),
            "rmse": float(rmse),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "point_count": self.capture_count,
        }
        CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        CALIBRATION_FILE.write_text(json.dumps(data, indent=2))
        log.info("Calibration saved — %d captures, RMSE %.4f px", self.capture_count, rmse)
        return data

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def capture_count(self) -> int:
        return len(self._captures)

    @property
    def ready(self) -> bool:
        return self.capture_count >= MIN_CAPTURES

    # ── Internal ───────────────────────────────────────────────────────────

    def _compute_homography(
        self,
        charuco_corners: np.ndarray,
        charuco_ids: np.ndarray,
        camera_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
    ) -> np.ndarray:
        """Compute undistorted-pixel → mat-mm homography from a flat board view."""
        board_world = self._board.getChessboardCorners()  # shape (N, 3), z=0

        img_pts: list[list[float]] = []
        obj_pts: list[list[float]] = []
        for i, cid in enumerate(charuco_ids.flatten()):
            if cid < len(board_world):
                wp = board_world[cid]
                obj_pts.append([float(wp[0]), float(wp[1])])
                img_pts.append(charuco_corners[i][0].tolist())

        if len(obj_pts) < 4:
            log.warning("Not enough points for homography — using identity")
            return np.eye(3)

        img_arr = np.array(img_pts, dtype=np.float32).reshape(-1, 1, 2)
        obj_arr = np.array(obj_pts, dtype=np.float32)

        # Undistort image points before finding homography
        undistorted = cv2.undistortPoints(
            img_arr, camera_matrix, dist_coeffs, P=camera_matrix
        ).reshape(-1, 2)

        H, mask = cv2.findHomography(undistorted, obj_arr, cv2.RANSAC, 5.0)
        if H is None:
            log.warning("Homography computation failed — using identity")
            return np.eye(3)

        inliers = int(mask.sum()) if mask is not None else 0
        log.info("Homography computed — %d / %d inliers", inliers, len(obj_pts))
        return H
