"""
OrcaSlicer CLI wrapper and OpenSCAD compiler.

Slice pipeline:
  1. Receive STL file path + print config
  2. Resolve full P1S machine/process/filament settings (flattening inheritance)
  3. Build a BambuStudio-compatible project .3mf with embedded preset JSONs
  4. Run: orca-slicer --slice 0 project.3mf --export-3mf output.3mf
  5. Return path to output .3mf

Embedding presets directly in the 3MF avoids the OrcaSlicer 2.3.2 CLI bug
where --load-settings machine.json;process.json causes a segfault at
update_values_to_printer_extruders_for_multiple_filaments.

Print profiles stored in D1 (jarvis-projects DB) via jarvis-api.
Support options: none | normal | tree (tree preferred for organic Meshy models).
"""
import asyncio
import contextlib
import io
import json
import os
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger(__name__)

ORCA_CLI      = os.getenv("ORCA_CLI", "/usr/bin/orca-slicer")
# Path to OrcaSlicer AppImage (preferred over extracted binary for headless).
ORCA_APPIMAGE = os.getenv("ORCA_APPIMAGE", "")
# Explicit DISPLAY for OrcaSlicer / Xvfb (e.g. ":99").
ORCA_DISPLAY  = os.getenv("ORCA_DISPLAY", "")
OPENSCAD_BIN  = os.getenv("OPENSCAD_BIN", "openscad")
# Explicit DISPLAY override for headless servers; falls back to inherited $DISPLAY.
OPENSCAD_DISPLAY = os.getenv("OPENSCAD_DISPLAY")

QUALITY_PROFILES = {
    "draft":    {"layer_height": "0.28", "speed": "300"},
    "standard": {"layer_height": "0.20", "speed": "200"},
    "fine":     {"layer_height": "0.10", "speed": "100"},
}

# Critical P1S settings not present anywhere in the BBL profile inheritance chain
# (come from OrcaSlicer's compiled-in FDM defaults, which default incorrectly for P1S).
_P1S_MACHINE_OVERRIDES: dict = {
    "use_relative_e_distances": "0",   # Bambu uses absolute E; default is 1 → error -51
    "machine_extruder_count": "1",
    "printer_technology": "FFF",
}


def orca_available() -> bool:
    if ORCA_APPIMAGE:
        return os.path.isfile(ORCA_APPIMAGE) and os.access(ORCA_APPIMAGE, os.X_OK)
    return os.path.isfile(ORCA_CLI) and os.access(ORCA_CLI, os.X_OK)


def openscad_available() -> bool:
    return shutil.which(OPENSCAD_BIN) is not None


def _openscad_supports_manifold() -> bool:
    """Return True if the installed OpenSCAD is 2022+ (has --backend=manifold)."""
    import re, subprocess as _sp
    try:
        out = _sp.run(
            [OPENSCAD_BIN, "--version"],
            capture_output=True, text=True, timeout=5,
        ).stderr + _sp.run(
            [OPENSCAD_BIN, "--version"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        m = re.search(r"(\d{4})\.", out)
        return bool(m and int(m.group(1)) >= 2022)
    except Exception:
        return False


def _orca_profiles_dir() -> Path:
    """
    Locate the Bambu Lab profile directory bundled with OrcaSlicer.

    Search order:
      1. ORCA_PROFILES_DIR env var (explicit override)
      2. resources/profiles/BBL/ next to the resolved ORCA_CLI binary
         (covers AppImage-extracted installs like /opt/orcaslicer/bin/orca-slicer)
      3. ~/.config/OrcaSlicer/system/BBL/ (user data dir, after first GUI run)
    """
    override = os.getenv("ORCA_PROFILES_DIR")
    if override:
        return Path(override)

    candidates: list[Path] = []
    try:
        candidates.append(Path(ORCA_CLI).resolve())
    except Exception:
        pass
    if ORCA_APPIMAGE:
        try:
            candidates.append(Path(ORCA_APPIMAGE).resolve())
        except Exception:
            pass
    for binary in candidates:
        try:
            for parent in [binary.parent, binary.parent.parent]:
                candidate = parent / "resources" / "profiles" / "BBL"
                if candidate.is_dir():
                    return candidate
        except Exception:
            pass

    return Path.home() / ".config" / "OrcaSlicer" / "system" / "BBL"


# ─────────────────────────────────────────────────────────────────────────────
# Profile resolution
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_profile(json_path: Path, profiles_dir: Path, _depth: int = 0) -> dict:
    """
    Load a profile JSON and flatten its full inheritance chain.
    Child settings override parent settings. Returns a merged dict.
    """
    if _depth > 20:
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    parent_name = data.get("inherits", "")
    if not parent_name:
        return dict(data)

    # Search for parent: same dir first, then anywhere under profiles_dir.
    parent_path: Optional[Path] = json_path.parent / f"{parent_name}.json"
    if not parent_path.exists():
        parent_path = None
        for cand in profiles_dir.rglob(f"{parent_name}.json"):
            parent_path = cand
            break

    if parent_path is None:
        return dict(data)

    parent = _resolve_profile(parent_path, profiles_dir, _depth + 1)
    merged = {**parent, **data}
    # Remove inherits so OrcaSlicer doesn't try to resolve it against the empty CLI DB.
    merged.pop("inherits", None)
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# STL parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_binary_stl(stl_path: str) -> "tuple[list[tuple], list[tuple]]":
    """
    Parse a binary STL file.
    Returns (vertex_list, triangle_list) with deduplicated vertices.
    """
    vmap: dict = {}
    vlist: list = []
    tlist: list = []
    with open(stl_path, "rb") as f:
        f.read(80)  # header
        (n_tri,) = struct.unpack_from("<I", f.read(4))
        for _ in range(n_tri):
            f.read(12)  # normal vector (ignored)
            indices = []
            for _ in range(3):
                xyz = struct.unpack_from("<fff", f.read(12))
                idx = vmap.setdefault(xyz, len(vlist))
                if idx == len(vlist):
                    vlist.append(xyz)
                indices.append(idx)
            f.read(2)   # attribute byte count
            tlist.append(tuple(indices))
    return vlist, tlist


# ─────────────────────────────────────────────────────────────────────────────
# Project 3MF builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_project_3mf(
    stl_path: str,
    machine: dict,
    process: dict,
    filament: dict,
) -> bytes:
    """
    Build a BambuStudio-compatible project 3MF as a bytes object.

    Embeds the STL geometry and fully-resolved preset JSONs so OrcaSlicer
    CLI can slice without --load-settings (avoiding the 2.3.2 combined
    machine+process segfault).

    Structure follows the real BambuStudio export format:
      3D/3dmodel.model        ← build structure, component reference (no mesh)
      3D/Objects/model.model  ← actual geometry (vertices + triangles)
      Metadata/model_settings.config
      Metadata/{machine,process,filament}_settings_0.json

    The production extension (requiredextensions="p") is required so the
    component p:path reference resolves.  The path must NOT have a leading
    slash — ZIP entries are stored without it and OrcaSlicer does an exact
    match against the archive entry name.
    """
    m_name  = machine.get("name", "Bambu Lab P1S 0.4 nozzle")
    pr_name = process.get("name", "0.20mm Standard @BBL X1C")
    fi_name = filament.get("name", "Bambu PLA Basic @BBL X1C")

    vlist, tlist = _parse_binary_stl(stl_path)

    # ── 3D/Objects/model.model  (geometry only) ──────────────────────────────
    geo_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
        '  <resources>',
        '    <object id="1" type="model">',
        '      <mesh>',
        '        <vertices>',
    ]
    for x, y, z in vlist:
        geo_parts.append(f'          <v x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>')
    geo_parts += ['        </vertices>', '        <triangles>']
    for v1, v2, v3 in tlist:
        geo_parts.append(f'          <t v1="{v1}" v2="{v2}" v3="{v3}"/>')
    geo_parts += [
        '        </triangles>',
        '      </mesh>',
        '    </object>',
        '  </resources>',
        '</model>',
    ]
    geometry_xml = "\n".join(geo_parts)

    # ── 3D/3dmodel.model  (assembly + build, production extension) ───────────
    # id="2" is the assembly object; it references the geometry object id="1"
    # from the external file via <component>.  <build> references the assembly.
    build_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' requiredextensions="p">\n'
        '  <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
        '  <resources>\n'
        '    <object id="2" type="model">\n'
        '      <components>\n'
        '        <component p:path="3D/Objects/model.model" objectid="1"/>\n'
        '      </components>\n'
        '    </object>\n'
        '  </resources>\n'
        '  <build>\n'
        '    <item objectid="2" transform="1 0 0 0 1 0 0 0 1 0 0 0"'
        ' BambuStudio:plate_index="0"/>\n'
        '  </build>\n'
        '</model>\n'
    )

    # ── Metadata/model_settings.config ────────────────────────────────────────
    model_cfg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        "  <plate>\n"
        '    <metadata key="plater_id" value="1"/>\n'
        '    <metadata key="plater_name" value=""/>\n'
        '    <metadata key="locked" value="false"/>\n'
        f'    <metadata key="printer_settings_id" value="{m_name}"/>\n'
        f'    <metadata key="print_settings_id" value="{pr_name}"/>\n'
        f'    <metadata key="filament_settings_id" value="{fi_name}"/>\n'
        '    <object id="2" instanceid="0">\n'
        '      <metadata key="name" value="model"/>\n'
        '      <metadata key="extruder" value="1"/>\n'
        '    </object>\n'
        '  </plate>\n'
        "</config>\n"
    )

    # ── [Content_Types].xml ───────────────────────────────────────────────────
    ctypes = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels"'
        ' ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="model"'
        ' ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '  <Default Extension="json" ContentType="application/json"/>\n'
        '  <Override PartName="/Metadata/model_settings.config"'
        ' ContentType="application/xml"/>\n'
        '</Types>\n'
    )

    # ── _rels/.rels ───────────────────────────────────────────────────────────
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Target="/3D/3dmodel.model" Id="rel-1"'
        ' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n'
    )

    # ── Pack ZIP ──────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ctypes)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("3D/3dmodel.model", build_xml)
        zf.writestr("3D/Objects/model.model", geometry_xml)
        zf.writestr("Metadata/model_settings.config", model_cfg)
        zf.writestr("Metadata/machine_settings_0.json",  json.dumps(machine,  indent=2))
        zf.writestr("Metadata/process_settings_0.json",  json.dumps(process,  indent=2))
        zf.writestr("Metadata/filament_settings_0.json", json.dumps(filament, indent=2))
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def slice_model(
    input_path: str,
    quality: str = "standard",
    infill: int = 15,
    supports: str = "none",
    output_dir: str = "/tmp",
) -> str:
    """
    Slice input_path (binary STL) with OrcaSlicer, return path to output .3mf.

    Slices input_path with fully-resolved flat preset JSONs written to temp
    files, passed via --load-settings.  Pre-resolving the full inheritance chain
    ourselves (removing the `inherits` key) means OrcaSlicer reads flat JSON
    with no internal resolution — avoiding the 2.3.2 segfault in
    update_values_to_printer_extruders_for_multiple_filaments that occurs when
    OrcaSlicer resolves the raw BBL inheritance chain.

    Set ORCA_APPIMAGE to use the AppImage directly (preferred for headless).
    Set ORCA_DISPLAY to override $DISPLAY (e.g. ":99" for Xvfb).
    Override profile root with ORCA_PROFILES_DIR env var.
    Timeout: 300 s.
    """
    if not orca_available():
        bin_hint = ORCA_APPIMAGE or ORCA_CLI
        raise RuntimeError(f"OrcaSlicer binary not found: {bin_hint!r}")

    profiles_dir = _orca_profiles_dir()

    process_file_map = {
        "draft":    "0.28mm Extra Draft @BBL X1C.json",
        "standard": "0.20mm Standard @BBL X1C.json",
        "fine":     "0.12mm Fine @BBL X1C.json",
    }
    process_file = process_file_map.get(quality, process_file_map["standard"])

    machine_json  = profiles_dir / "machine"  / "Bambu Lab P1S 0.4 nozzle.json"
    filament_json = profiles_dir / "filament" / "Bambu PLA Basic @BBL X1C.json"
    process_json  = profiles_dir / "process"  / process_file

    # Flatten the full inheritance chain for each profile.
    machine  = _resolve_profile(machine_json,  profiles_dir)
    process  = _resolve_profile(process_json,  profiles_dir)
    filament = _resolve_profile(filament_json, profiles_dir)

    # Guarantee correct name fields (may be overwritten by a parent profile).
    machine["name"]  = "Bambu Lab P1S 0.4 nozzle"
    process["name"]  = process_file.removesuffix(".json")
    filament["name"] = "Bambu PLA Basic @BBL X1C"

    # Apply P1S-critical settings absent from the file-based inheritance chain.
    machine.update(_P1S_MACHINE_OVERRIDES)

    # Per-job overrides.
    process["sparse_infill_density"] = str(infill)
    if supports == "none":
        process["enable_support"] = "0"
    elif supports == "normal":
        process["enable_support"] = "1"
        process["support_type"]   = "normal(auto)"
    elif supports == "tree":
        process["enable_support"] = "1"
        process["support_type"]   = "tree(auto)"

    stem        = Path(input_path).stem
    output_path = str(Path(output_dir) / f"{stem}.3mf")

    # Write fully-resolved flat JSON profiles to temp files.  OrcaSlicer will
    # read them as-is — no `inherits` key means no internal resolution, which
    # avoids the 2.3.2 CLI segfault in update_values_to_printer_extruders_
    # for_multiple_filaments that occurs when resolution touches the multi-
    # extruder code path.
    m_fd, m_tmp = tempfile.mkstemp(suffix=".json", prefix="orca_machine_")
    p_fd, p_tmp = tempfile.mkstemp(suffix=".json", prefix="orca_process_")
    f_fd, f_tmp = tempfile.mkstemp(suffix=".json", prefix="orca_filament_")
    try:
        os.write(m_fd, json.dumps(machine).encode()); os.close(m_fd); m_fd = -1
        os.write(p_fd, json.dumps(process).encode()); os.close(p_fd); p_fd = -1
        os.write(f_fd, json.dumps(filament).encode()); os.close(f_fd); f_fd = -1

        orca_bin = ORCA_APPIMAGE if ORCA_APPIMAGE else ORCA_CLI
        settings_arg = f"{m_tmp};{p_tmp};{f_tmp}"
        cmd = [
            orca_bin,
            "--slice", "0",
            "--load-settings", settings_arg,
            "--export-3mf", output_path,
            input_path,
        ]
        log.info("OrcaSlicer slice: %s", " ".join(cmd))

        env = dict(os.environ)
        if ORCA_DISPLAY:
            env["DISPLAY"] = ORCA_DISPLAY

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=300.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError("OrcaSlicer timed out after 300 s")

        stdout_text = stdout_bytes.decode(errors="replace")
        stderr_text = stderr_bytes.decode(errors="replace")
        combined = (stdout_text + "\n" + stderr_text).strip()
        out = Path(output_path)

        if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            log.error("OrcaSlicer failed (rc=%d)\nstdout: %s\nstderr: %s",
                      proc.returncode, stdout_text, stderr_text)
            raise RuntimeError(
                f"OrcaSlicer slicing failed (rc={proc.returncode}): {combined}"
            )

        log.info("3MF written: %s (%d bytes)", output_path, out.stat().st_size)
        return output_path

    finally:
        for fd, path in [(m_fd, m_tmp), (p_fd, p_tmp), (f_fd, f_tmp)]:
            if fd >= 0:
                with contextlib.suppress(OSError):
                    os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(path)


async def compile_openscad(scad_code: str, output_path: str) -> str:
    """
    Write scad_code to a temp .scad file, compile to binary STL via openscad CLI.
    Returns output_path on success. Raises RuntimeError on failure or timeout.
    """
    if not openscad_available():
        raise RuntimeError(f"OpenSCAD binary not found: {OPENSCAD_BIN!r}")

    env = dict(os.environ)
    if OPENSCAD_DISPLAY:
        env["DISPLAY"] = OPENSCAD_DISPLAY

    scad_file = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".scad", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(scad_code)
            scad_file = f.name

        cmd = [OPENSCAD_BIN]
        if _openscad_supports_manifold():
            cmd.append("--backend=manifold")
        cmd += ["--export-format", "binstl", "-o", output_path, scad_file]
        log.info("OpenSCAD compile: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            _stdout, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=120.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError("OpenSCAD timed out after 120 s")

        stderr_text = stderr_bytes.decode(errors="replace")
        out = Path(output_path)

        if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            log.error("OpenSCAD failed (rc=%d): %s", proc.returncode, stderr_text)
            raise RuntimeError(
                f"OpenSCAD compilation failed (rc={proc.returncode}): {stderr_text.strip()}"
            )

        log.info("STL written: %s (%d bytes)", output_path, out.stat().st_size)
        return output_path

    finally:
        if scad_file:
            with contextlib.suppress(OSError):
                os.unlink(scad_file)
