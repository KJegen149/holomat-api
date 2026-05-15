#!/usr/bin/env python3
"""
Option A proof-of-concept: slice a 1 cm cube, upload to Bambu P1S via FTP,
and trigger the print via MQTT.

Usage (on KJLC-AI-01):
  BAMBU_IP=10.11.12.91 \
  BAMBU_ACCESS_CODE=14620600 \
  BAMBU_SERIAL=01P00C5C0701414 \
  ORCA_DISPLAY=:99 \
  python3 scripts/test_bambu_print.py

Environment variables (all have defaults matching the lab printer):
  BAMBU_IP           Printer LAN IP          (default: 10.11.12.91)
  BAMBU_ACCESS_CODE  8-digit access code     (default: 14620600)
  BAMBU_SERIAL       Printer serial number   (default: 01P00C5C0701414)
  ORCA_CLI           orca-slicer binary path (default: /usr/bin/orca-slicer)
  ORCA_DISPLAY       DISPLAY used by slicer  (default: :99)
  DRY_RUN=1          Slice only, skip FTP+MQTT
"""
import asyncio
import math
import os
import struct
import sys
import tempfile
from pathlib import Path

# Allow running from repo root or scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Defaults for lab printer ───────────────────────────────────────────────────
os.environ.setdefault("BAMBU_IP",          "10.11.12.91")
os.environ.setdefault("BAMBU_ACCESS_CODE", "14620600")
os.environ.setdefault("BAMBU_SERIAL",      "01P00C5C0701414")
os.environ.setdefault("ORCA_CLI",          "/usr/bin/orca-slicer")

DRY_RUN = os.getenv("DRY_RUN", "").strip() not in ("", "0", "false", "no")

from core.slicer import orca_available, slice_model  # noqa: E402
from core.printer import _ftp_upload, _mqtt_print_trigger  # noqa: E402


# ── Minimal 1 cm cube STL ──────────────────────────────────────────────────────

_CUBE_FACES = [
    ((0, 0, -1), (0, 0, 0), (1, 0, 0), (0, 1, 0)),
    ((0, 0, -1), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
    ((0, 0,  1), (0, 0, 1), (0, 1, 1), (1, 0, 1)),
    ((0, 0,  1), (1, 0, 1), (0, 1, 1), (1, 1, 1)),
    ((0, -1, 0), (0, 0, 0), (0, 0, 1), (1, 0, 0)),
    ((0, -1, 0), (1, 0, 0), (0, 0, 1), (1, 0, 1)),
    ((0,  1, 0), (0, 1, 0), (1, 1, 0), (0, 1, 1)),
    ((0,  1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)),
    ((-1, 0, 0), (0, 0, 0), (0, 1, 0), (0, 0, 1)),
    ((-1, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)),
    ((1,  0, 0), (1, 0, 0), (1, 0, 1), (1, 1, 0)),
    ((1,  0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)),
]


def _make_cube_stl() -> str:
    fd, path = tempfile.mkstemp(suffix=".stl", prefix="bambu_test_cube_")
    with os.fdopen(fd, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(_CUBE_FACES)))
        for n, v1, v2, v3 in _CUBE_FACES:
            for c in n:
                f.write(struct.pack("<f", float(c)))
            for vtx in (v1, v2, v3):
                for c in vtx:
                    f.write(struct.pack("<f", float(c) * 10.0))  # 10 mm cube
            f.write(b"\x00\x00")
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=== Bambu P1S end-to-end test ===\n")

    bambu_ip     = os.environ["BAMBU_IP"]
    access_code  = os.environ["BAMBU_ACCESS_CODE"]
    serial       = os.environ["BAMBU_SERIAL"]

    print(f"Printer : {bambu_ip}  serial={serial}  access={access_code}")
    print(f"Dry-run : {DRY_RUN}\n")

    # 1. Check slicer
    if not orca_available():
        print(f"FAIL: OrcaSlicer not found at {os.getenv('ORCA_CLI', '/usr/bin/orca-slicer')!r}")
        sys.exit(1)
    print("OK  OrcaSlicer found")

    # 2. Generate test STL
    stl_path = _make_cube_stl()
    print(f"OK  Cube STL created: {stl_path}")

    try:
        # 3. Slice
        print("\n--- Slicing (standard quality, 15% infill, tree supports) ---")
        three_mf_path = await slice_model(
            input_path=stl_path,
            quality="standard",
            infill=15,
            supports="tree",
            output_dir="/tmp",
        )
        size_bytes = Path(three_mf_path).stat().st_size
        print(f"OK  Sliced → {three_mf_path}  ({size_bytes:,} bytes)")

        if DRY_RUN:
            print("\nDRY RUN — skipping FTP upload and MQTT trigger.")
            print("SUCCESS (dry run)")
            return

        # 4. FTP upload
        print("\n--- Uploading via FTP ---")
        remote_filename = _ftp_upload(three_mf_path)
        print(f"OK  Uploaded → /cache/{remote_filename}")

        # 5. MQTT print trigger
        print("\n--- Triggering print via MQTT ---")
        _mqtt_print_trigger(remote_filename)
        print(f"OK  Print triggered: {remote_filename}")

        print("\nSUCCESS — cube sent to printer.")
        print("Check the Bambu Handy app or printer touchscreen to confirm.")

    finally:
        if os.path.exists(stl_path):
            os.unlink(stl_path)


asyncio.run(main())
