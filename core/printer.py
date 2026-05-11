"""
Bambu Lab P1S wrapper — MQTT status polling and FTP+MQTT print job submission.

Status:   bambulabs-api (MQTT subscribe, receives push reports)
Printing: ftplib (file upload to printer cache) + paho-mqtt (print trigger)
"""
import asyncio
import ftplib
import json
import os
import ssl
import time
import uuid
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger(__name__)

BAMBU_IP          = os.getenv("BAMBU_IP", "")
BAMBU_ACCESS_CODE = os.getenv("BAMBU_ACCESS_CODE", "")
BAMBU_SERIAL      = os.getenv("BAMBU_SERIAL", "")
BAMBU_CERT        = os.getenv("BAMBU_CERT", "certs/printer.pem")
BAMBU_FTP_PORT    = int(os.getenv("BAMBU_FTP_PORT", "21"))
BAMBU_MQTT_PORT   = int(os.getenv("BAMBU_MQTT_PORT", "8883"))


def is_configured() -> bool:
    return bool(BAMBU_IP and BAMBU_ACCESS_CODE and BAMBU_SERIAL)


async def get_status() -> dict:
    """
    Connect to printer via MQTT, wait for a status push, return state dict.
    Returns {state, nozzle_temp, bed_temp, progress, current_file}.
    """
    try:
        import bambulabs_api as bl  # type: ignore
    except ImportError:
        return {"error": "bambulabs-api not installed"}

    if not is_configured():
        return {"error": "Bambu credentials not configured"}

    loop = asyncio.get_running_loop()

    def _poll() -> dict:
        printer = bl.Printer(
            ip_address=BAMBU_IP,
            access_code=BAMBU_ACCESS_CODE,
            serial=BAMBU_SERIAL,
        )
        try:
            printer.connect()
            for _ in range(16):
                if printer.mqtt_client_ready:
                    break
                time.sleep(0.5)

            state = str(printer.get_current_state())
            # Strip enum prefix e.g. "GcodeState.IDLE" → "IDLE"
            if "." in state:
                state = state.split(".")[-1]

            current_file: Optional[str] = None
            if hasattr(printer, "get_gcode_file"):
                try:
                    current_file = printer.get_gcode_file()
                except Exception:
                    pass

            return {
                "state": state,
                "nozzle_temp": printer.get_nozzle_temperature(),
                "bed_temp": printer.get_bed_temperature(),
                "progress": printer.get_percentage(),
                "current_file": current_file,
            }
        finally:
            try:
                printer.disconnect()
            except Exception:
                pass

    try:
        return await loop.run_in_executor(None, _poll)
    except Exception as e:
        log.error("Printer status error: %s", e)
        return {"error": str(e)}


# ── FTP upload ───────────────────────────────────────────────────────────────

def _ftp_upload(path_3mf: str) -> str:
    """Upload 3MF to printer /cache/ via FTPS. Returns filename on printer."""
    filename = Path(path_3mf).name
    ftp = ftplib.FTP_TLS()
    ftp.connect(host=BAMBU_IP, port=BAMBU_FTP_PORT, timeout=30)
    ftp.login(user="bblp", passwd=BAMBU_ACCESS_CODE)
    ftp.prot_p()  # enable TLS data channel protection
    with open(path_3mf, "rb") as f:
        ftp.storbinary(f"STOR /cache/{filename}", f)
    ftp.quit()
    log.info("FTP upload OK: /cache/%s", filename)
    return filename


# ── MQTT print trigger ────────────────────────────────────────────────────────

def _mqtt_print_trigger(filename: str) -> None:
    """Send project_file command over MQTT to trigger the print job."""
    try:
        import paho.mqtt.client as mqtt  # type: ignore
    except ImportError:
        raise RuntimeError("paho-mqtt not installed — pip install paho-mqtt")

    connected = False

    def _on_connect(client, userdata, flags, *args):
        nonlocal connected
        # args[0] is rc (int, paho v1) or ReasonCode (paho v2)
        rc = args[0] if args else 0
        connected = (rc == 0 if isinstance(rc, int) else rc.value == 0)

    # Build client — support both paho-mqtt v1 and v2
    try:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined]
            client_id=f"holomat_{uuid.uuid4().hex[:8]}",
        )
    except AttributeError:
        client = mqtt.Client(client_id=f"holomat_{uuid.uuid4().hex[:8]}")

    client.on_connect = _on_connect
    client.username_pw_set("bblp", BAMBU_ACCESS_CODE)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    cert_path = Path(BAMBU_CERT)
    if cert_path.exists():
        ctx.load_verify_locations(str(cert_path))
    client.tls_set_context(ctx)

    client.connect(BAMBU_IP, BAMBU_MQTT_PORT, keepalive=30)
    client.loop_start()

    deadline = time.time() + 10
    while not connected and time.time() < deadline:
        time.sleep(0.1)

    if not connected:
        client.loop_stop()
        raise RuntimeError("MQTT connect to printer timed out after 10 s")

    subtask = filename.replace(".3mf", "")
    msg = {
        "print": {
            "sequence_id": "0",
            "command": "project_file",
            "param": "Metadata/plate_1.gcode",
            "subtask_name": subtask,
            "url": f"ftp:///cache/{filename}",
            "timelapse": False,
            "bed_leveling": True,
            "flow_cali": False,
            "vibration_cali": False,
            "layer_inspect": False,
            "use_ams": False,
        }
    }
    topic = f"device/{BAMBU_SERIAL}/request"
    result = client.publish(topic, json.dumps(msg), qos=0)
    result.wait_for_publish(timeout=5)
    client.loop_stop()
    client.disconnect()
    log.info("MQTT print trigger sent: %s → %s", topic, filename)


# ── Public async API ─────────────────────────────────────────────────────────

async def send_and_print(path_3mf: str) -> dict:
    """
    Upload .3mf to printer /cache/ via FTPS, then trigger print via MQTT.
    Returns {status, filename}.
    """
    if not is_configured():
        raise RuntimeError(
            "Bambu printer not configured — set BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL"
        )
    loop = asyncio.get_running_loop()
    filename = await loop.run_in_executor(None, _ftp_upload, path_3mf)
    await loop.run_in_executor(None, _mqtt_print_trigger, filename)
    return {"status": "sent", "filename": filename}
