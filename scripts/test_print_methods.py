#!/usr/bin/env python3
"""
Three-method print-dispatch test — run in order to find what works on current firmware.

  Phase 1 — Cloud MQTT (ACS-signed)  → auto-start if cert accepted
  Phase 2 — Panda Touch probe        → discover any HTTP API
  Phase 3 — LAN MQTT (Developer Mode)→ direct printer control

Usage:
  python3 scripts/test_print_methods.py [--phase 1|2|3] [--dry-run]

Defaults: runs all phases.  --dry-run skips actual print dispatch.

Environment:
  BAMBU_EMAIL         Bambu account email         (phase 1)
  BAMBU_PASSWORD      Bambu account password       (phase 1)
  BAMBU_SERIAL        Printer serial               (all)
  BAMBU_IP            Printer LAN IP               (phase 3)
  BAMBU_ACCESS_CODE   Printer access code          (phase 3)
  PANDA_TOUCH_IP      Panda Touch LAN IP           (phase 2, default 10.11.12.197)
"""
import argparse
import asyncio
import json
import logging
import os
import socket
import struct
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BAMBU_SERIAL",      "01P00C5C0701414")
os.environ.setdefault("BAMBU_IP",          "10.11.12.91")
os.environ.setdefault("BAMBU_ACCESS_CODE", "14620600")
os.environ.setdefault("ORCA_CLI",          "/usr/bin/orca-slicer")

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
log = logging.getLogger("test_print_methods")

PANDA_TOUCH_IP = os.getenv("PANDA_TOUCH_IP", "10.11.12.197")


# ── Minimal 1 cm cube STL ──────────────────────────────────────────────────────

_CUBE_FACES = [
    ((0,0,-1),(0,0,0),(1,0,0),(0,1,0)), ((0,0,-1),(1,0,0),(1,1,0),(0,1,0)),
    ((0,0, 1),(0,0,1),(0,1,1),(1,0,1)), ((0,0, 1),(1,0,1),(0,1,1),(1,1,1)),
    ((0,-1,0),(0,0,0),(0,0,1),(1,0,0)), ((0,-1,0),(1,0,0),(0,0,1),(1,0,1)),
    ((0, 1,0),(0,1,0),(1,1,0),(0,1,1)), ((0, 1,0),(1,1,0),(1,1,1),(0,1,1)),
    ((-1,0,0),(0,0,0),(0,1,0),(0,0,1)), ((-1,0,0),(0,1,0),(0,1,1),(0,0,1)),
    ((1, 0,0),(1,0,0),(1,0,1),(1,1,0)), ((1, 0,0),(1,0,1),(1,1,1),(1,1,0)),
]

def _make_cube_stl() -> str:
    fd, path = tempfile.mkstemp(suffix=".stl", prefix="holomat_test_")
    with os.fdopen(fd, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(_CUBE_FACES)))
        for n, v1, v2, v3 in _CUBE_FACES:
            for c in n:  f.write(struct.pack("<f", float(c)))
            for vtx in (v1, v2, v3):
                for c in vtx: f.write(struct.pack("<f", float(c) * 10.0))
            f.write(b"\x00\x00")
    return path


def _sep(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print('─'*60)


# ── Phase 1: Cloud MQTT with ACS signing ──────────────────────────────────────

async def phase1_cloud(three_mf: str, dry_run: bool) -> bool:
    _sep("PHASE 1 — Cloud MQTT (ACS-signed project_file)")

    from core.printer import is_cloud_configured
    if not is_cloud_configured():
        print("SKIP — BAMBU_EMAIL / BAMBU_PASSWORD not set")
        return False

    print(f"Account : {os.environ.get('BAMBU_EMAIL')}")
    print(f"Serial  : {os.environ.get('BAMBU_SERIAL')}")

    if dry_run:
        print("DRY RUN — skipping dispatch")
        return False

    try:
        from core.printer import _cloud_send_and_print
        result = _cloud_send_and_print(three_mf)
        print(f"\nOK  Dispatch returned: {result}")
        print("\n>>> Watch the printer — did it start automatically? (y/n)")
        ans = input("Result: ").strip().lower()
        success = ans.startswith("y")
        print("PHASE 1 RESULT:", "AUTO-STARTED ✓" if success else "still waiting / failed ✗")
        return success
    except Exception as e:
        print(f"FAIL: {e}")
        return False


# ── Phase 2: Panda Touch probe ────────────────────────────────────────────────

def phase2_panda_touch(dry_run: bool) -> bool:
    _sep(f"PHASE 2 — Panda Touch probe ({PANDA_TOUCH_IP})")
    import urllib.request, urllib.error

    # 1. Check reachability
    try:
        s = socket.create_connection((PANDA_TOUCH_IP, 80), timeout=3)
        s.close()
        print(f"OK  Port 80 open on {PANDA_TOUCH_IP}")
    except (ConnectionRefusedError, OSError) as e:
        print(f"FAIL: Port 80 not reachable — {e}")
        print("      Check PANDA_TOUCH_IP env var or that the device is on the network")
        return False

    # 2. Probe candidate endpoints
    probes = [
        ("GET", "/",                    "Root page"),
        ("GET", "/api",                 "API root"),
        ("GET", "/api/status",          "Status endpoint"),
        ("GET", "/api/printer",         "Printer info"),
        ("GET", "/api/print",           "Print control"),
        ("GET", "/status",              "Alt status"),
        ("GET", "/control",             "Control endpoint"),
        ("GET", "/confirm",             "Confirm endpoint"),
        ("GET", "/printer/confirm",     "Printer confirm"),
        ("POST", "/api/confirm",        "POST confirm"),
        ("POST", "/api/print/confirm",  "POST print confirm"),
        ("GET", "/info",                "Info page"),
        ("GET", "/settings",            "Settings page"),
    ]

    found: list[tuple] = []
    for method, path, label in probes:
        url = f"http://{PANDA_TOUCH_IP}{path}"
        try:
            req = urllib.request.Request(url, method=method,
                                         data=b"{}" if method == "POST" else None,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read(500).decode(errors="replace")
                print(f"  {method:5} {path:35} → HTTP {resp.status}  body={body[:80]!r}")
                found.append((method, path, resp.status, body))
        except urllib.error.HTTPError as e:
            print(f"  {method:5} {path:35} → HTTP {e.code}")
            if e.code not in (404, 405):
                found.append((method, path, e.code, ""))
        except Exception:
            pass  # timeout / connection refused = not there

    print()
    if found:
        print(f"Found {len(found)} responding endpoint(s)")
        for method, path, status, body in found:
            if status < 400:
                print(f"  *** LIVE: {method} {path} → {status}")
        print("\n>>> Does the Panda Touch have any useful API? (y/n/describe)")
        ans = input("Result: ").strip().lower()
        return ans.startswith("y")
    else:
        print("No API endpoints found — Panda Touch has no HTTP control interface")
        return False


# ── Phase 3: LAN MQTT (Developer Mode) ───────────────────────────────────────

async def phase3_lan(three_mf: str, dry_run: bool) -> bool:
    _sep("PHASE 3 — LAN MQTT direct (Developer Mode on printer)")

    from core.printer import is_lan_configured
    if not is_lan_configured():
        print("SKIP — BAMBU_IP / BAMBU_ACCESS_CODE not set")
        return False

    print(f"Printer : {os.environ.get('BAMBU_IP')}  serial={os.environ.get('BAMBU_SERIAL')}")
    print("NOTE: Make sure Developer Mode is enabled on the printer touchscreen")
    print("      Settings → Network → LAN Only Mode → Developer Mode\n")

    if dry_run:
        print("DRY RUN — skipping dispatch")
        return False

    try:
        from core.printer import _ftp_upload, _mqtt_print_trigger
        print("Uploading via FTP...")
        remote = _ftp_upload(three_mf)
        print(f"OK  Uploaded → /cache/{remote}")

        print("Sending MQTT project_file command...")
        _mqtt_print_trigger(remote)
        print("OK  MQTT trigger sent")

        print("\n>>> Watch the printer — did it start automatically (no touchscreen tap)? (y/n)")
        ans = input("Result: ").strip().lower()
        success = ans.startswith("y")
        print("PHASE 3 RESULT:", "AUTO-STARTED ✓" if success else "touchscreen required / failed ✗")
        return success
    except Exception as e:
        print(f"FAIL: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], help="Run only one phase")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual print dispatch")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  Holomat Print Method Test  —  firmware 1.08")
    print("="*60)

    from core.slicer import orca_available, slice_model
    if not orca_available():
        print("FAIL: OrcaSlicer not found")
        sys.exit(1)

    stl = _make_cube_stl()
    print(f"\nSlicing test cube...")
    three_mf = await slice_model(stl, quality="standard", infill=15,
                                  supports="none", output_dir="/tmp",
                                  ams_slot=int(os.getenv("BAMBU_AMS_SLOT", "0")))
    print(f"OK  {three_mf}  ({Path(three_mf).stat().st_size:,} bytes)")

    results = {}
    try:
        if args.phase in (None, 1):
            results[1] = await phase1_cloud(three_mf, args.dry_run)
        if args.phase in (None, 2):
            results[2] = phase2_panda_touch(args.dry_run)
        if args.phase in (None, 3):
            results[3] = await phase3_lan(three_mf, args.dry_run)
    finally:
        for p in [stl, three_mf]:
            try: os.unlink(p)
            except: pass

    _sep("SUMMARY")
    labels = {1: "Cloud MQTT (ACS-signed)", 2: "Panda Touch API", 3: "LAN MQTT (Dev Mode)"}
    for phase, ok in results.items():
        mark = "✓ WORKS" if ok else "✗ no auto-start"
        print(f"  Phase {phase}: {labels[phase]:30}  {mark}")
    print()

asyncio.run(main())
