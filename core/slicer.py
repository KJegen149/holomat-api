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

ORCA_CLI = os.getenv("ORCA_CLI", "/usr/bin/orca-slicer")
OPENSCAD_BIN = os.getenv("OPENSCAD_BIN", "openscad")
# Explicit DISPLAY override for headless servers; falls back to inherited $DISPLAY.
OPENSCAD_DISPLAY = os.getenv("OPENSCAD_DISPLAY")

QUALITY_PROFILES = {
    "draft":    {"layer_height": "0.28", "speed": "300"},
    "standard": {"layer_height": "0.20", "speed": "200"},
    "fine":     {"layer_height": "0.10", "speed": "100"},
}


def orca_available() -> bool:
    return os.path.isfile(ORCA_CLI) and os.access(ORCA_CLI, os.X_OK)


def openscad_available() -> bool:
    return shutil.which(OPENSCAD_BIN) is not None


async def slice_model(
    input_path: str,
    quality: str = "standard",
    infill: int = 15,
    supports: str = "none",
    output_dir: str = "/tmp",
) -> str:
    """
    Run OrcaSlicer CLI on input_path, return path to output .3mf.
    Implemented in Phase 7.
    """
    raise NotImplementedError("Phase 7")


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

        cmd = [
            OPENSCAD_BIN,
            "--backend=manifold",
            "--export-format", "binstl",
            "-o", output_path,
            scad_file,
        ]
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
