"""
OrcaSlicer CLI wrapper.

Slice pipeline:
  1. Receive STL or GLB file path + print config
  2. Run: orca-slicer --slice 0 [params] model.stl --export-3mf output.3mf
  3. Return path to output .3mf

Print profiles stored in D1 (jarvis-projects DB) via jarvis-api.
Support options: none | normal | tree (tree preferred for organic Meshy models).

Implemented in Phase 5.
"""
import os
import shutil
from pathlib import Path

from core.logger import get_logger

log = get_logger(__name__)

ORCA_CLI = os.getenv("ORCA_CLI", "/usr/bin/orca-slicer")
OPENSCAD_BIN = os.getenv("OPENSCAD_BIN", "openscad")

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
    Implemented in Phase 5.
    """
    raise NotImplementedError("Phase 5")


async def compile_openscad(scad_code: str, output_path: str) -> str:
    """
    Write scad_code to a temp file, compile to STL via openscad CLI.
    Returns path to STL. Implemented in Phase 5.
    """
    raise NotImplementedError("Phase 5")
