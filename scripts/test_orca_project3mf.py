#!/usr/bin/env python3
"""
Test OrcaSlicer project-3MF slicing on KJLC-AI-01.

Usage:
  ORCA_APPIMAGE=/tmp/orcaslicer.AppImage \
  ORCA_DISPLAY=:99 \
  python3 scripts/test_orca_project3mf.py [optional_input.stl]

Creates a tiny test STL (1cm cube) if no input file is provided,
then slices it via the new project-3MF code path and reports the result.
"""
import os, struct, sys, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.slicer import (
    orca_available, _orca_profiles_dir, _resolve_profile,
    _parse_binary_stl, _build_project_3mf, _P1S_MACHINE_OVERRIDES, slice_model,
)

# ── Build a minimal 1cm×1cm×1cm binary STL cube ──────────────────────────────
CUBE_FACES = [
    # (normal, v1, v2, v3)
    ((0,0,-1),(0,0,0),(1,0,0),(0,1,0)),
    ((0,0,-1),(1,0,0),(1,1,0),(0,1,0)),
    ((0,0,1),(0,0,1),(0,1,1),(1,0,1)),
    ((0,0,1),(1,0,1),(0,1,1),(1,1,1)),
    ((0,-1,0),(0,0,0),(0,0,1),(1,0,0)),
    ((0,-1,0),(1,0,0),(0,0,1),(1,0,1)),
    ((0,1,0),(0,1,0),(1,1,0),(0,1,1)),
    ((0,1,0),(1,1,0),(1,1,1),(0,1,1)),
    ((-1,0,0),(0,0,0),(0,1,0),(0,0,1)),
    ((-1,0,0),(0,1,0),(0,1,1),(0,0,1)),
    ((1,0,0),(1,0,0),(1,0,1),(1,1,0)),
    ((1,0,0),(1,0,1),(1,1,1),(1,1,0)),
]

def make_test_stl() -> str:
    fd, path = tempfile.mkstemp(suffix=".stl", prefix="orca_test_cube_")
    with os.fdopen(fd, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(CUBE_FACES)))
        for n, v1, v2, v3 in CUBE_FACES:
            for coord in n:
                f.write(struct.pack("<f", float(coord)))
            for v in (v1, v2, v3):
                for coord in v:
                    f.write(struct.pack("<f", float(coord) * 10.0))  # 10mm cube
            f.write(b"\x00\x00")
    return path


async def main():
    print("=== OrcaSlicer project-3MF test ===\n")

    # 1. Check binary
    if not orca_available():
        print("FAIL: OrcaSlicer binary not found")
        print(f"  ORCA_APPIMAGE={os.getenv('ORCA_APPIMAGE','')}")
        print(f"  ORCA_CLI={os.getenv('ORCA_CLI','/usr/bin/orca-slicer')}")
        sys.exit(1)
    print("OK  OrcaSlicer binary found")

    # 2. Check profiles dir
    pdir = _orca_profiles_dir()
    print(f"    Profiles dir: {pdir}")
    if not pdir.is_dir():
        print("FAIL: profiles directory not found")
        sys.exit(1)
    print("OK  Profiles directory found")

    # 3. Resolve profiles
    machine_json  = pdir / "machine"  / "Bambu Lab P1S 0.4 nozzle.json"
    process_json  = pdir / "process"  / "0.20mm Standard @BBL X1C.json"
    filament_json = pdir / "filament" / "Bambu PLA Basic @BBL X1C.json"
    for label, p in [("machine", machine_json), ("process", process_json), ("filament", filament_json)]:
        if not p.exists():
            print(f"FAIL: {label} profile not found: {p}")
            sys.exit(1)

    machine  = _resolve_profile(machine_json,  pdir)
    process  = _resolve_profile(process_json,  pdir)
    filament = _resolve_profile(filament_json, pdir)
    machine["name"]  = "Bambu Lab P1S 0.4 nozzle"
    process["name"]  = "0.20mm Standard @BBL X1C"
    filament["name"] = "Bambu PLA Basic @BBL X1C"
    machine.update(_P1S_MACHINE_OVERRIDES)

    print(f"OK  Profiles resolved")
    print(f"    machine keys:  {len(machine)}")
    print(f"    process keys:  {len(process)}")
    print(f"    filament keys: {len(filament)}")
    print(f"    use_relative_e_distances = {machine.get('use_relative_e_distances','NOT SET')}")
    print(f"    machine_extruder_count   = {machine.get('machine_extruder_count','NOT SET')}")

    # 4. Build project 3MF
    stl_path = sys.argv[1] if len(sys.argv) > 1 else make_test_stl()
    cleanup_stl = len(sys.argv) < 2
    try:
        vlist, tlist = _parse_binary_stl(stl_path)
        print(f"OK  STL parsed: {len(vlist)} vertices, {len(tlist)} triangles")

        import tempfile as _tmp, zipfile as _zip
        proj_bytes = _build_project_3mf(stl_path, machine, process, filament)
        print(f"OK  Project 3MF built: {len(proj_bytes):,} bytes")

        # Peek inside the ZIP to verify structure
        with _zip.ZipFile(__import__("io").BytesIO(proj_bytes)) as zf:
            names = zf.namelist()
        print(f"    ZIP contents: {names}")

        # 5. Run OrcaSlicer
        print("\n--- Running OrcaSlicer ---")
        out_path = await slice_model(
            input_path=stl_path,
            quality="standard",
            infill=15,
            supports="none",
            output_dir="/tmp",
        )
        import pathlib
        sz = pathlib.Path(out_path).stat().st_size
        print(f"\nSUCCESS: {out_path}  ({sz:,} bytes)")
    finally:
        if cleanup_stl and os.path.exists(stl_path):
            os.unlink(stl_path)


asyncio.run(main())
