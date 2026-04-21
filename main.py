#!/usr/bin/env python3
"""
HoloMat Pipeline API Server  v0.1
Runs on KJLC-AI-01 (10.11.12.129) port 8100

Endpoints:
  GET  /health            — liveness + config check
  GET  /printer/status    — live P1S status via MQTT
  POST /print             — full print pipeline (Phase 2A)
  POST /generate          — OpenSCAD → STL (Phase 2B)
"""
import asyncio
import io
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Config (all overridable via env vars in the systemd unit) ─────────────────

BASE_DIR     = Path(__file__).parent
PRINTER_IP   = os.getenv("BAMBU_IP",          "10.11.12.91")
ACCESS_CODE  = os.getenv("BAMBU_ACCESS_CODE", "14620600")
SERIAL       = os.getenv("BAMBU_SERIAL",      "01p00c5c0701414")
CERT_PATH    = os.getenv("BAMBU_CERT",        str(BASE_DIR / "certs" / "printer.pem"))
CF_API_URL   = os.getenv("CF_API_URL",        "https://jarvis-api.kjeg.workers.dev")
CF_API_KEY   = os.getenv("CF_API_KEY",        "")
ORCA_CLI     = os.getenv("ORCA_CLI",          "/usr/bin/orca-slicer")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="HoloMat Pipeline API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness check — also reports config state so dashboard can warn early."""
    try:
        import bambulabs_api  # noqa
        bambu_installed = True
    except ImportError:
        bambu_installed = False

    return {
        "status": "ok",
        "version": "0.1.0",
        "printer_ip":       PRINTER_IP,
        "serial":           SERIAL,
        "cert_exists":      Path(CERT_PATH).exists(),
        "orca_exists":      Path(ORCA_CLI).exists(),
        "bambu_lib":        bambu_installed,
        "cf_key_set":       bool(CF_API_KEY),
    }


@app.get("/printer/status")
async def printer_status():
    """
    Connect to P1S via MQTT, wait for a status packet, return it.
    Times out after 8 seconds if the printer doesn't respond.
    """
    try:
        import bambulabs_api as bl
    except ImportError:
        raise HTTPException(500, "bambulabs-api not installed")

    try:
        printer = bl.Printer(
            ip_address=PRINTER_IP,
            access_code=ACCESS_CODE,
            serial=SERIAL,
        )
        printer.connect()

        # Wait up to 8 s for MQTT ready
        for _ in range(16):
            await asyncio.sleep(0.5)
            if printer.mqtt_client_ready:
                break

        try:
            data = {
                "state":    printer.get_current_state(),
                "nozzle":   printer.get_nozzle_temperature(),
                "bed":      printer.get_bed_temperature(),
                "progress": printer.get_percentage(),
                "file":     printer.gcode_file,
            }
        except Exception as e:
            data = {"read_error": str(e)}

        printer.disconnect()
        return {"online": True, "data": data}

    except Exception as e:
        return {"online": False, "error": str(e)}


# ── Print pipeline ─────────────────────────────────────────────────────────────

class PrintRequest(BaseModel):
    file_id:    str
    filename:   str
    file_type:  str = "stl"        # stl | 3mf
    quality:    str = "standard"   # draft | standard | fine (used when slicing added)
    infill:     str = "15"         # percent
    supports:   str = "none"       # none | auto | everywhere
    project_id: str | None = None


QUALITY_PROFILES = {
    "draft":    "0.28mm",
    "standard": "0.20mm",
    "fine":     "0.12mm",
}


@app.post("/print")
async def dispatch_print(req: PrintRequest):
    """
    Phase 2A print pipeline:
      1. Download STL from Cloudflare R2 via Worker  ← implemented
      2. Slice with OrcaSlicer CLI                   ← TODO (needs install)
      3. Upload .3mf to P1S via FTP                  ← TODO (after step 2)
      4. Trigger print via MQTT                      ← TODO (after step 3)
    """
    if not CF_API_KEY:
        raise HTTPException(500, "CF_API_KEY not set — add it to the systemd unit Environment=")

    # ── Step 1: Download STL ─────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{CF_API_URL}/api/files/{req.file_id}",
            headers={"X-API-Key": CF_API_KEY},
        )
    if r.status_code != 200:
        raise HTTPException(502, f"CF file download failed: HTTP {r.status_code}")

    stl_bytes = r.content
    stl_size  = len(stl_bytes)

    # ── Step 2: Use pre-sliced .3mf if available, otherwise require one ─────
    # Phase 2A: server-side slicing deferred. User slices in Bambu Studio and
    # uploads the .3mf. This endpoint accepts file_id of either an .stl OR .3mf.
    # If an STL was passed, check the project for a paired .3mf.
    is_3mf = req.filename.lower().endswith('.3mf') or req.file_type == '3mf'

    if not is_3mf:
        raise HTTPException(422, {
            "error":    "Pre-sliced .3mf required",
            "received": req.filename,
            "message":  "Slice your model in Bambu Studio → export .3mf → upload to this project, then print.",
        })

    threemf_bytes = stl_bytes   # already downloaded — it's actually the .3mf
    stl_size      = len(threemf_bytes)

    # ── Steps 3 + 4: Upload + Print via bambulabs-api ────────────────────────
    try:
        import bambulabs_api as bl
    except ImportError:
        raise HTTPException(500, "bambulabs-api not installed")

    try:
        printer = bl.Printer(
            ip_address=PRINTER_IP,
            access_code=ACCESS_CODE,
            serial=SERIAL,
        )
        printer.connect()

        for _ in range(10):
            await asyncio.sleep(0.5)
            if printer.mqtt_client_ready:
                break

        remote_name = req.filename.replace(".stl", ".gcode.3mf")
        printer.upload_file(io.BytesIO(threemf_bytes), remote_name)
        printer.start_print(remote_name, plate_number=1)
        printer.disconnect()

        return {
            "status":    "sent",
            "filename":  remote_name,
            "stl_bytes": stl_size,
            "profile":   profile,
            "infill":    req.infill,
            "supports":  req.supports,
        }

    except Exception as e:
        raise HTTPException(500, f"Printer communication failed: {e}")


# ── Generate (Phase 2B — OpenSCAD → STL) ─────────────────────────────────────

class GenerateRequest(BaseModel):
    code:       str
    filename:   str = "model.stl"
    project_id: str | None = None


@app.post("/generate")
async def generate_stl(req: GenerateRequest):
    """
    Phase 2B: Render OpenSCAD code to STL, upload to CF R2, return file_id.
    Requires: openscad installed on KJLC-AI-01 (`apt install openscad`).
    """
    openscad = os.getenv("OPENSCAD_BIN", "openscad")

    try:
        result = subprocess.run([openscad, "--version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            raise FileNotFoundError
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise HTTPException(503, {
            "error":     "openscad not installed",
            "phase":     "2B",
            "next_step": "sudo apt install openscad",
        })

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp       = Path(tmpdir)
        scad_path = tmp / "model.scad"
        stl_path  = tmp / req.filename

        scad_path.write_text(req.code)
        result = subprocess.run(
            [openscad, "-o", str(stl_path), str(scad_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise HTTPException(400, {"error": "OpenSCAD render failed", "stderr": result.stderr[-2000:]})
        if not stl_path.exists():
            raise HTTPException(500, "OpenSCAD ran but produced no STL")

        stl_bytes = stl_path.read_bytes()

    if not CF_API_KEY or not req.project_id:
        # Return raw bytes as base64 if no CF upload target
        import base64
        return {"stl_b64": base64.b64encode(stl_bytes).decode(), "filename": req.filename}

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{CF_API_URL}/api/projects/{req.project_id}/files",
            headers={
                "X-API-Key":   CF_API_KEY,
                "X-File-Name": req.filename,
                "X-File-Type": "stl",
            },
            content=stl_bytes,
        )
    if r.status_code not in (200, 201):
        raise HTTPException(502, f"CF upload failed: HTTP {r.status_code}")

    return r.json()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8100, reload=False)
