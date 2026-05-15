#!/usr/bin/env python3
"""
Cloud-mode proof-of-concept: authenticate with Bambu cloud, upload a 1 cm cube
.3mf, and dispatch the print job (auto-starts on printer, no touchscreen needed).

Usage:
  BAMBU_EMAIL=you@email.com \
  BAMBU_PASSWORD=yourpassword \
  BAMBU_SERIAL=01P00C5C0701414 \
  python3 scripts/test_bambu_cloud.py

Optional:
  DRY_RUN=1          Auth + upload only, skip print dispatch
  BAMBU_REGION=global  "global" (default) or "china"

Note: The printer must be in cloud+LAN hybrid mode (NOT LAN-only mode).
Switch via: Printer touchscreen → Settings → Network → (disable LAN Only Mode)
"""
import asyncio
import math
import os
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BAMBU_SERIAL", "01P00C5C0701414")
os.environ.setdefault("BAMBU_REGION", "global")

DRY_RUN = os.getenv("DRY_RUN", "").strip() not in ("", "0", "false", "no")

# Also set LAN vars so the slicer AMS slot injection still works
os.environ.setdefault("BAMBU_IP",          "10.11.12.91")
os.environ.setdefault("BAMBU_ACCESS_CODE", "14620600")
os.environ.setdefault("ORCA_CLI",          "/usr/bin/orca-slicer")

from core.slicer import orca_available, slice_model  # noqa: E402
from core.printer import is_cloud_configured, _get_bambu_client, _cloud_send_and_print  # noqa: E402
import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")


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
    fd, path = tempfile.mkstemp(suffix=".stl", prefix="bambu_cloud_test_")
    with os.fdopen(fd, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(_CUBE_FACES)))
        for n, v1, v2, v3 in _CUBE_FACES:
            for c in n:
                f.write(struct.pack("<f", float(c)))
            for vtx in (v1, v2, v3):
                for c in vtx:
                    f.write(struct.pack("<f", float(c) * 10.0))
            f.write(b"\x00\x00")
    return path


async def main() -> None:
    print("=== Bambu P1S cloud-mode end-to-end test ===\n")

    if not is_cloud_configured():
        print("FAIL: Cloud credentials not set.")
        print("  Set BAMBU_EMAIL, BAMBU_PASSWORD, BAMBU_SERIAL environment variables.")
        sys.exit(1)

    email  = os.environ["BAMBU_EMAIL"]
    serial = os.environ["BAMBU_SERIAL"]
    region = os.environ.get("BAMBU_REGION", "global")
    print(f"Account : {email}  region={region}")
    print(f"Printer : serial={serial}")
    print(f"Dry-run : {DRY_RUN}\n")

    # 1. Check cloud auth
    print("--- Authenticating with Bambu cloud ---")
    try:
        client = _get_bambu_client()
        print("OK  Authenticated (token cached)")
    except Exception as e:
        print(f"FAIL: Auth error: {e}")
        sys.exit(1)

    # 2. Check slicer
    if not orca_available():
        print(f"FAIL: OrcaSlicer not found at {os.getenv('ORCA_CLI', '/usr/bin/orca-slicer')!r}")
        sys.exit(1)
    print("OK  OrcaSlicer found")

    # 3. Generate test STL
    stl_path = _make_cube_stl()
    print(f"OK  Cube STL created: {stl_path}")

    try:
        # 4. Slice
        print("\n--- Slicing (standard quality, 15% infill) ---")
        three_mf_path = await slice_model(
            input_path=stl_path,
            quality="standard",
            infill=15,
            supports="none",
            output_dir="/tmp",
            ams_slot=int(os.getenv("BAMBU_AMS_SLOT", "0")),
        )
        size_bytes = Path(three_mf_path).stat().st_size
        print(f"OK  Sliced → {three_mf_path}  ({size_bytes:,} bytes)")

        if DRY_RUN:
            print("\nDRY RUN — skipping cloud upload and print dispatch.")
            print("SUCCESS (dry run)")
            return

        # 5. Cloud upload + dispatch
        print("\n--- Uploading to Bambu cloud and dispatching print ---")
        result = _cloud_send_and_print(three_mf_path)
        print(f"OK  Uploaded → {result['filename']}")
        print(f"OK  Print dispatched — job_id={result.get('job_id')}  status={result.get('cloud_status')}")

        print("\nSUCCESS — print job sent via cloud.")
        print("The printer should start automatically (no touchscreen confirmation needed).")
        print("Monitor via Bambu Handy app or printer display.")

    finally:
        if os.path.exists(stl_path):
            os.unlink(stl_path)


asyncio.run(main())
