"""
OrcaSlicer CLI wrapper and OpenSCAD compiler.

Slice pipeline:
  1. Receive STL file path + print config
  2. Patch BBL P1S profiles on disk (idempotent): use_relative_e_distances=0,
     G92 E0 in layer_gcode — satisfies the OrcaSlicer settings validator.
  3. Build a plain 3MF (inline geometry, canonical <vertex>/<triangle> tags).
  4. Run: orca-slicer --slice 0 --no-check project.3mf --export-3mf output.3mf
  5. Return path to output .3mf

Plain 3MF (no BambuStudio:3mfVersion marker) is used because the BBS code
path in OrcaSlicer 2.3.2 does not load cross-file component geometry in
headless CLI mode (always shows "0 objects").  --load-settings is NOT used
because passing machine JSON causes a segfault in 2.3.2
(update_values_to_printer_extruders_for_multiple_filaments).

Settings come from the active preset selected in ~/.config/OrcaSlicer/ (set
by running the GUI once and choosing "Bambu Lab P1S 0.4 nozzle").

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

def _ensure_orca_conf_presets(config_dir: Path, machine: str, print_: str, filament: str) -> None:
    """
    Ensure OrcaSlicer.conf has a complete "presets" object so CLI mode binds
    the right active preset under --datadir.  The first-run GUI wizard often
    saves only "machine" (omitting "print"/"filament"), which leaves CLI mode
    running on compiled-in defaults. Idempotent.
    """
    conf_path = config_dir / "OrcaSlicer.conf"
    if not conf_path.is_file():
        return
    try:
        data = json.loads(conf_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Cannot parse %s: %s", conf_path, e)
        return

    presets = data.get("presets") or {}
    desired = {"machine": machine, "print": print_, "filament": filament}
    if all(presets.get(k) == v for k, v in desired.items()):
        return  # already correct

    presets.update(desired)
    data["presets"] = presets
    try:
        conf_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        log.info("Updated OrcaSlicer.conf presets: %s", desired)
    except OSError as e:
        log.warning("Cannot write %s: %s", conf_path, e)


def _patch_bbl_profiles_for_p1s(profiles_dir: Path, process_file: str) -> None:
    """
    Patch BBL profiles on disk so OrcaSlicer's CLI validator accepts the slice.

    Two conditions satisfy the validator (either is sufficient):
      1. machine profile sets use_relative_e_distances=0
      2. process profile's layer_gcode contains "G92 E0"

    Patching the leaf machine profile alone has been observed to be ineffective
    on OrcaSlicer 2.3.2 — the compiled-in default of 1 persists for reasons
    that aren't visible at debug level 5.  Patching both gives belt-and-suspenders.

    Idempotent — no-op if already patched.
    """
    machine_path = profiles_dir / "machine" / "Bambu Lab P1S 0.4 nozzle.json"
    if machine_path.exists():
        try:
            data = json.loads(machine_path.read_text(encoding="utf-8"))
            if data.get("use_relative_e_distances") != "0":
                data["use_relative_e_distances"] = "0"
                machine_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                log.info("Patched %s: set use_relative_e_distances=0", machine_path)
        except OSError as e:
            log.warning("Cannot patch machine profile (permissions on %s): %s", machine_path, e)
        except Exception as e:
            log.warning("Unexpected error patching machine profile: %s", e)
    else:
        log.warning("P1S machine profile not found at %s", machine_path)

    process_path = profiles_dir / "process" / process_file
    if process_path.exists():
        try:
            data = json.loads(process_path.read_text(encoding="utf-8"))
            current = data.get("layer_gcode") or ""
            if "G92 E0" not in current:
                data["layer_gcode"] = "G92 E0\n" + (current if current else "")
                process_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                log.info("Patched %s: prepended G92 E0 to layer_gcode", process_path)
        except OSError as e:
            log.warning("Cannot patch process profile (permissions on %s): %s", process_path, e)
        except Exception as e:
            log.warning("Unexpected error patching process profile: %s", e)
    else:
        log.warning("Process profile not found at %s", process_path)


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
    Build a plain 3MF with inline geometry.

    Deliberately omits the BambuStudio:3mfVersion marker — the BBS code path
    in OrcaSlicer 2.3.2 uses cross-file component references that don't load
    in headless CLI mode (shows "0 objects").  Plain 3MF is confirmed to load
    geometry correctly (rc goes from -50 "nothing to slice" to -51 when settings
    are wrong).  Settings come from the active preset in ~/.config/OrcaSlicer/
    (set when the user ran the GUI for first-time setup).  The BBL P1S profiles
    are patched on disk (use_relative_e_distances=0, G92 E0 in layer_gcode) so
    the validator passes once the active preset is the P1S profile.
    """
    m_name  = machine.get("name", "Bambu Lab P1S 0.4 nozzle")
    pr_name = process.get("name", "0.20mm Standard @BBL X1C")
    fi_name = filament.get("name", "Bambu PLA Basic @BBL X1C")

    vlist, tlist = _parse_binary_stl(stl_path)

    # ── 3D/3dmodel.model  (inline geometry — plain 3MF) ──────────────────────
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
        '  <resources>',
        '    <object id="1" type="model">',
        '      <mesh>',
        '        <vertices>',
    ]
    for x, y, z in vlist:
        parts.append(f'          <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>')
    parts += ['        </vertices>', '        <triangles>']
    for v1, v2, v3 in tlist:
        parts.append(f'          <triangle v1="{v1}" v2="{v2}" v3="{v3}"/>')
    parts += [
        '        </triangles>',
        '      </mesh>',
        '    </object>',
        '  </resources>',
        '  <build>',
        '    <item objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>',
        '  </build>',
        '</model>',
    ]
    model_xml = "\n".join(parts)

    # NOTE: model_settings.config intentionally omitted — when present, it
    # declares printer_settings_id/print_settings_id that OrcaSlicer tries to
    # match against loaded presets by name, failing the compatibility check
    # if names differ. With --load-settings driving all configuration, the 3MF
    # should be pure geometry.

    # ── [Content_Types].xml ───────────────────────────────────────────────────
    ctypes = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels"'
        ' ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="model"'
        ' ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '</Types>\n'
    )

    # ── _rels/.rels ───────────────────────────────────────────────────────────
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships'
        ' xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Target="/3D/3dmodel.model" Id="rel-1"'
        ' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ctypes)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("3D/3dmodel.model", model_xml)
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

    Approach: plain 3MF (inline geometry, no BambuStudio:3mfVersion marker).
    OrcaSlicer uses whatever preset is active in ~/.config/OrcaSlicer/, which
    must be set up by running the GUI once and selecting "Bambu Lab P1S 0.4
    nozzle".  BBL P1S profiles are patched on disk (idempotent) to satisfy
    the settings validator (use_relative_e_distances=0, G92 E0 in layer_gcode).

    Set ORCA_APPIMAGE to use the AppImage directly (preferred for headless).
    Set ORCA_DISPLAY to override $DISPLAY (e.g. ":99" for Xvfb).
    Override profile root with ORCA_PROFILES_DIR env var.
    Timeout: 300 s.
    """
    if not orca_available():
        bin_hint = ORCA_APPIMAGE or ORCA_CLI
        raise RuntimeError(f"OrcaSlicer binary not found: {bin_hint!r}")

    # OrcaSlicer 2.3.2 CLI requires a pre-selected preset in its config dir;
    # without GUI setup, it runs on compiled-in defaults that fail the
    # settings validator ("Add G92 E0 to layer_gcode").
    # Check multiple candidate homes in case service user ≠ GUI user.
    _config_candidates = [
        Path.home() / ".config" / "OrcaSlicer",
        Path("/home/user/.config/OrcaSlicer"),
        Path("/root/.config/OrcaSlicer"),
    ]
    config_dir = next(
        (d for d in _config_candidates if d.exists() and any(
            p.is_file() and p.suffix in (".conf", ".json")
            for p in d.iterdir()
        )),
        None,
    )
    if config_dir is None:
        raise RuntimeError(
            "OrcaSlicer config dir not found or has no preset selection — "
            "CLI slicing will fail validation. Launch the OrcaSlicer GUI once "
            "(e.g. `DISPLAY=:99 /usr/bin/orca-slicer` over VNC/X-forwarding), "
            "complete the first-run wizard selecting 'Bambu Lab P1S 0.4 nozzle', "
            "save and quit. Then retry. "
            f"Checked: {[str(d) for d in _config_candidates]}"
        )
    log.debug("OrcaSlicer config dir: %s", config_dir)

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

    # Patch the BBL P1S profiles on disk so the validator passes.  Idempotent.
    _patch_bbl_profiles_for_p1s(profiles_dir, process_file)

    # Ensure OrcaSlicer.conf fully selects the P1S preset trio. Idempotent.
    _ensure_orca_conf_presets(
        config_dir,
        machine="Bambu Lab P1S 0.4 nozzle",
        print_=process_file.removesuffix(".json"),
        filament="Bambu PLA Basic @BBL X1C",
    )

    # Flatten the full inheritance chain for each profile (for embedded JSONs).
    machine  = _resolve_profile(machine_json,  profiles_dir)
    process  = _resolve_profile(process_json,  profiles_dir)
    filament = _resolve_profile(filament_json, profiles_dir)

    machine["name"]  = "Bambu Lab P1S 0.4 nozzle"
    process["name"]  = process_file.removesuffix(".json")
    filament["name"] = "Bambu PLA Basic @BBL X1C"

    machine.update(_P1S_MACHINE_OVERRIDES)

    process["sparse_infill_density"] = str(infill)
    process["use_relative_e_distances"] = "0"
    process["layer_gcode"] = "G92 E0\n"
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

    project_bytes = _build_project_3mf(input_path, machine, process, filament)

    # Build minimal machine + process JSONs for --load-settings.
    #
    # Process-only failed with rc=239 "process not compatible with printer"
    # despite compatible_printers=[] / compatible_printers_condition="" — the
    # CLI check at slic3r.cpp:2559 appears to compare loaded process against
    # the current (empty) printer name and fail.
    #
    # We pass a *minimal* machine JSON (just the keys needed to satisfy the
    # validator + compatibility check, no AMS/filament arrays). The previous
    # SIGSEGV was with the fully-flattened 106-key BBL machine; a stripped
    # machine with 1 extruder / 1 filament should not trigger the crash path
    # in update_values_to_printer_extruders_for_multiple_filaments.
    machine_for_cli = {
        "type": "machine",
        "name": "Bambu Lab P1S 0.4 nozzle",
        "from": "User",
        "inherits": "",
        "instantiation": "true",
        "version": "2.3.2.0",
        "printer_technology": "FFF",
        "printer_model": "Bambu Lab P1S",
        "printer_variant": "0.4",
        "machine_extruder_count": "1",
        "single_extruder_multi_material": "0",
        "use_relative_e_distances": "0",
        "printable_area": ["0x0", "256x0", "256x256", "0x256"],
        "printable_height": "250",
        "nozzle_diameter": ["0.4"],
        "extruder_offset": ["0x0"],
        "retraction_length": ["0.8"],
        "retraction_speed": ["30"],
        "deretraction_speed": ["30"],
    }

    process_for_cli = dict(process)
    process_for_cli["type"] = "process"
    process_for_cli["name"] = "holomat_p1s_process"
    process_for_cli["from"] = "User"
    process_for_cli["inherits"] = ""
    process_for_cli["instantiation"] = "true"
    process_for_cli["compatible_printers"] = ["Bambu Lab P1S 0.4 nozzle"]
    process_for_cli["compatible_printers_condition"] = ""
    process_for_cli["layer_gcode"] = "G92 E0\n"
    process_for_cli["use_relative_e_distances"] = "0"
    process_for_cli["version"] = "2.3.2.0"
    process_for_cli["printer_settings_id"] = "Bambu Lab P1S 0.4 nozzle"

    # Deterministic paths so failed runs leave a debuggable footprint.
    mach_settings_path = "/tmp/orca_holomat_machine.json"
    proc_settings_path = "/tmp/orca_holomat_process.json"
    with open(mach_settings_path, "w") as _f:
        json.dump(machine_for_cli, _f, indent=2)
    with open(proc_settings_path, "w") as _f:
        json.dump(process_for_cli, _f, indent=2)

    fd, project_path = tempfile.mkstemp(suffix=".3mf", prefix="orca_proj_")
    try:
        os.write(fd, project_bytes)
        os.close(fd)
        fd = -1

        orca_bin = ORCA_APPIMAGE if ORCA_APPIMAGE else ORCA_CLI
        # --load-settings takes machine;process (semicolon-separated)
        cmd = [
            orca_bin,
            "--datadir", str(config_dir),
            "--load-settings", f"{mach_settings_path};{proc_settings_path}",
            "--slice", "0",
            "--export-3mf", output_path,
            project_path,
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
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(project_path)
        # Settings JSONs are kept at /tmp/orca_holomat_*.json for debugging.


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
