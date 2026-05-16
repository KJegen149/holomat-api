#!/usr/bin/env python3
"""
End-to-end print test: slice a 1 cm cube and send it to the Bambu P1S.

Reads all credentials from .env (or environment). No hardcoded values.

Usage:
  python3 scripts/test_bambu_print.py [--dry-run]

  --dry-run   Slice only; skip FTP upload and MQTT trigger.

Requires: BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL, BAMBU_EMAIL, BAMBU_PASSWORD
"""
import argparse
import asyncio
import os
import struct
import sys
import tempfile
from pathlib import Path

# Load .env before importing core modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

from core.slicer import orca_available, slice_model
from core.printer import is_lan_configured, send_and_print


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
    fd, path = tempfile.mkstemp(suffix=".stl", prefix="holomat_test_")
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Slice only, skip dispatch")
    args = parser.parse_args()

    print("=== Holomat — Bambu P1S end-to-end test ===\n")

    if not is_lan_configured():
        print("FAIL: LAN credentials not set.")
        print("  Ensure BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL are in .env")
        sys.exit(1)

    if not orca_available():
        print(f"FAIL: OrcaSlicer not found at {os.getenv('ORCA_CLI', '/usr/bin/orca-slicer')!r}")
        sys.exit(1)

    ams_slot = int(os.getenv("BAMBU_AMS_SLOT", "0"))
    print(f"Printer : {os.getenv('BAMBU_IP')}  serial={os.getenv('BAMBU_SERIAL')}")
    print(f"AMS slot: {ams_slot}")
    print(f"Dry-run : {args.dry_run}\n")

    stl_path = _make_cube_stl()
    print(f"OK  Test cube STL: {stl_path}")

    try:
        print("\n--- Slicing ---")
        three_mf = await slice_model(
            input_path=stl_path,
            quality="standard",
            infill=15,
            supports="none",
            output_dir="/tmp",
            ams_slot=ams_slot,
        )
        print(f"OK  {three_mf}  ({Path(three_mf).stat().st_size:,} bytes)")

        if args.dry_run:
            print("\nDRY RUN — skipping dispatch.")
            return

        print("\n--- Uploading and triggering print ---")
        result = await send_and_print(three_mf, ams_slot=ams_slot)
        print(f"OK  Dispatched: {result}")
        print("\nSUCCESS — watch the printer start automatically.")

    finally:
        for p in [stl_path]:
            try:
                os.unlink(p)
            except OSError:
                pass


asyncio.run(main())
