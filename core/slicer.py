"""
OrcaSlicer CLI wrapper and OpenSCAD compiler.

Slice pipeline:
  1. Receive STL or GLB file path + print config
  2. Run: orca-slicer --slice 0 [params] model.stl --export-3mf output.3mf
  3. Return path to output .3mf

Print profiles stored in D1 (jarvis-projects DB) via jarvis-api.
Support options: none | normal | tree (tree preferred for organic Meshy models).
"""
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

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


def _orca_profiles_dir() -> "Path":
    """
    Locate the Bambu Lab profile directory bundled with OrcaSlicer.

    Search order:
      1. ORCA_PROFILES_DIR env var (explicit override)
      2. resources/profiles/BBL/ next to the resolved ORCA_CLI binary
         (covers AppImage-extracted installs like /opt/orcaslicer/bin/orca-slicer)
      3. ~/.config/OrcaSlicer/system/BBL/ (user data dir, after first GUI run)
    """
    import os as _os
    from pathlib import Path as _Path

    override = _os.getenv("ORCA_PROFILES_DIR")
    if override:
        return _Path(override)

    # Walk up from the real binary (or AppImage sibling dir) to find resources/profiles/BBL
    candidates: list[_Path] = []
    try:
        candidates.append(_Path(ORCA_CLI).resolve())
    except Exception:
        pass
    if ORCA_APPIMAGE:
        try:
            candidates.append(_Path(ORCA_APPIMAGE).resolve())
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

    # Fall back to user config dir (populated after first GUI run)
    return _Path.home() / ".config" / "OrcaSlicer" / "system" / "BBL"


async def slice_model(
    input_path: str,
    quality: str = "standard",
    infill: int = 15,
    supports: str = "none",
    output_dir: str = "/tmp",
) -> str:
    """
    Run OrcaSlicer CLI on input_path, return path to output .3mf.

    Set ORCA_APPIMAGE to use the AppImage directly (preferred for headless).
    Set ORCA_DISPLAY to override $DISPLAY (e.g. ":99" for Xvfb).
    Override profile root with ORCA_PROFILES_DIR env var.
    Timeout: 300 s.
    """
    if not orca_available():
        bin_hint = ORCA_APPIMAGE or ORCA_CLI
        raise RuntimeError(f"OrcaSlicer binary not found: {bin_hint!r}")

    from pathlib import Path as _Path

    profiles_dir = _orca_profiles_dir()

    # OrcaSlicer 2.3.2 ships no P1S-specific process profiles.
    # The P1S is listed as compatible in X1C process profiles (same hotend/motion).
    process_file_map = {
        "draft":    "0.28mm Extra Draft @BBL X1C.json",
        "standard": "0.20mm Standard @BBL X1C.json",
        "fine":     "0.12mm Fine @BBL X1C.json",
    }
    process_file = process_file_map.get(quality, process_file_map["standard"])

    machine_src  = profiles_dir / "machine"  / "Bambu Lab P1S 0.4 nozzle.json"
    filament_src = profiles_dir / "filament" / "Bambu PLA Basic @BBL X1C.json"
    process_src  = profiles_dir / "process"  / process_file

    stem = _Path(input_path).stem
    output_path = str(_Path(output_dir) / f"{stem}.3mf")

    # Stage profile subdirectories under a temp path that contains no vendor
    # prefix (no "BBL" component).  When OrcaSlicer is run as an AppImage it
    # strips its own internal vendor prefix from absolute --load-settings paths;
    # staging under /tmp sidesteps that normalisation.
    staged = tempfile.mkdtemp(prefix="orca_prof_")
    try:
        for subdir, src in [
            ("machine",  machine_src.parent),
            ("filament", filament_src.parent),
            ("process",  process_src.parent),
        ]:
            dest = _Path(staged) / subdir
            if src.is_dir():
                os.symlink(str(src), str(dest))

        staged_machine  = _Path(staged) / "machine"  / machine_src.name
        staged_filament = _Path(staged) / "filament" / filament_src.name
        staged_process  = _Path(staged) / "process"  / process_src.name

        orca_bin = ORCA_APPIMAGE if ORCA_APPIMAGE else ORCA_CLI
        cmd = [orca_bin, "--slice", "0"]

        # OrcaSlicer uses --load-settings for machine+process (semicolon-joined)
        # and --load-filaments for filament profiles.
        settings_parts = [p for p in [staged_machine, staged_process] if p.exists()]
        if settings_parts:
            cmd += ["--load-settings", ";".join(str(p) for p in settings_parts)]
        if staged_filament.exists():
            cmd += ["--load-filaments", str(staged_filament)]

        cmd += ["--export-3mf", output_path, input_path]
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
            _stdout, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=300.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError("OrcaSlicer timed out after 300 s")

        stderr_text = stderr_bytes.decode(errors="replace")
        out = _Path(output_path)

        if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            log.error("OrcaSlicer failed (rc=%d): %s", proc.returncode, stderr_text)
            raise RuntimeError(
                f"OrcaSlicer slicing failed (rc={proc.returncode}): {stderr_text.strip()}"
            )

        log.info("3MF written: %s (%d bytes)", output_path, out.stat().st_size)
        return output_path

    finally:
        shutil.rmtree(staged, ignore_errors=True)


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
        # --backend=manifold requires OpenSCAD 2022+; skip on older builds
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
            try:
                os.unlink(scad_file)
            except OSError:
                pass
