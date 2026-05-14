#!/usr/bin/env python3
"""
Test OrcaSlicer project-3MF slicing on KJLC-AI-01.

Usage:
  ORCA_APPIMAGE=/tmp/orcaslicer.AppImage \
  ORCA_DISPLAY=:99 \
  python3 scripts/test_orca_project3mf.py [optional_input.stl]

Creates test STLs (1cm cube + 15mm sphere) if no input file is provided,
then slices each via slice_model() and reports the results.
"""
import math, os, struct, sys, asyncio, tempfile
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


def make_sphere_stl(radius_mm: float = 15.0, stacks: int = 16, slices: int = 16) -> str:
    """Generate a UV sphere binary STL. Non-planar geometry stress-tests the parser."""
    faces = []
    def v(stack_i, slice_j):
        phi   = math.pi * stack_i / stacks        # 0 .. pi
        theta = 2 * math.pi * slice_j / slices    # 0 .. 2pi
        x = radius_mm * math.sin(phi) * math.cos(theta)
        y = radius_mm * math.sin(phi) * math.sin(theta)
        z = radius_mm * math.cos(phi)
        return (x, y, z + radius_mm)  # shift up so base sits at z=0

    def normal(va, vb, vc):
        ax, ay, az = vb[0]-va[0], vb[1]-va[1], vb[2]-va[2]
        bx, by, bz = vc[0]-va[0], vc[1]-va[1], vc[2]-va[2]
        nx, ny, nz = ay*bz-az*by, az*bx-ax*bz, ax*by-ay*bx
        L = math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
        return (nx/L, ny/L, nz/L)

    for i in range(stacks):
        for j in range(slices):
            v00, v01 = v(i, j), v(i, j+1)
            v10, v11 = v(i+1, j), v(i+1, j+1)
            if i != 0:
                faces.append((normal(v00, v11, v10), v00, v11, v10))
            if i != stacks - 1:
                faces.append((normal(v00, v01, v11), v00, v01, v11))

    fd, path = tempfile.mkstemp(suffix=".stl", prefix="orca_test_sphere_")
    with os.fdopen(fd, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(faces)))
        for n, v1, v2, v3 in faces:
            for coord in n:
                f.write(struct.pack("<f", float(coord)))
            for vtx in (v1, v2, v3):
                for coord in vtx:
                    f.write(struct.pack("<f", float(coord)))
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

    import pathlib, zipfile as _zip

    # If an STL was provided on the command line, just slice that one.
    if len(sys.argv) > 1:
        shapes = [("custom", sys.argv[1], False)]
    else:
        cube_path   = make_test_stl()
        sphere_path = make_sphere_stl()
        shapes = [
            ("cube (10mm)",   cube_path,   True),
            ("sphere (15mm)", sphere_path, True),
        ]

    all_ok = True
    for label, stl_path, cleanup in shapes:
        print(f"\n── Shape: {label} ─────────────────────────────────")
        try:
            vlist, tlist = _parse_binary_stl(stl_path)
            print(f"OK  STL parsed: {len(vlist)} vertices, {len(tlist)} triangles")

            proj_bytes = _build_project_3mf(stl_path, machine, process, filament)
            print(f"OK  Project 3MF built: {len(proj_bytes):,} bytes")

            with _zip.ZipFile(__import__("io").BytesIO(proj_bytes)) as zf:
                print(f"    ZIP contents: {zf.namelist()}")

            print("--- Running OrcaSlicer ---")
            out_path = await slice_model(
                input_path=stl_path,
                quality="standard",
                infill=15,
                supports="none",
                output_dir="/tmp",
            )
            sz = pathlib.Path(out_path).stat().st_size
            print(f"SUCCESS: {out_path}  ({sz:,} bytes)")
        except Exception as e:
            print(f"FAIL: {e}")
            all_ok = False
        finally:
            if cleanup and os.path.exists(stl_path):
                os.unlink(stl_path)

    print()
    if all_ok:
        print("All shapes sliced successfully — pipeline ready.")
    else:
        print("One or more shapes failed.")
        sys.exit(1)


asyncio.run(main())
