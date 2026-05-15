"""
Bambu Lab P1S wrapper — MQTT status polling and FTP+MQTT print job submission.

Status:   bambulabs-api (MQTT subscribe, receives push reports)
Printing: ftplib (file upload to printer cache) + paho-mqtt (print trigger)
"""
import asyncio
import ftplib
import json
import os
import socket
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
BAMBU_FTP_PORT    = int(os.getenv("BAMBU_FTP_PORT", "990"))   # implicit FTPS
BAMBU_MQTT_PORT   = int(os.getenv("BAMBU_MQTT_PORT", "8883"))
# AMS slot index (0 = first tray of first AMS unit, 1 = second tray, etc.)
# Set to -1 to disable AMS and print from the external spool holder.
BAMBU_AMS_SLOT    = int(os.getenv("BAMBU_AMS_SLOT", "0"))


class _ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS variant that wraps the control socket in TLS immediately (implicit FTPS).

    Standard FTP_TLS uses explicit mode (AUTH TLS command after plain connect).
    Bambu Lab printers speak implicit FTPS on port 990 — TLS from the first byte.
    """

    def connect(self, host: str = "", port: int = 0,
                timeout: float = -999, source_address=None) -> str:
        if host:
            self.host = host
        if port:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        if source_address is not None:
            self.source_address = source_address
        # Wrap socket in TLS before sending any FTP data
        raw = socket.create_connection(
            (self.host, self.port), self.timeout, self.source_address
        )
        self.sock = self.context.wrap_socket(raw, server_hostname=self.host)
        self.af   = self.sock.family
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def storbinary(self, cmd, fp, blocksize=8192, callback=None, rest=None):
        # Identical to FTP_TLS.storbinary except the data-channel TLS shutdown
        # uses a 2 s timeout — Bambu's FTP server never sends close_notify, so
        # the default unwrap() blocks until the socket timeout (30 s) expires.
        self.voidcmd("TYPE I")
        with self.transfercmd(cmd, rest) as conn:
            while True:
                buf = fp.read(blocksize)
                if not buf:
                    break
                conn.sendall(buf)
                if callback:
                    callback(buf)
            if isinstance(conn, ssl.SSLSocket):
                conn.settimeout(2)
                try:
                    conn.unwrap()
                except (TimeoutError, OSError, ssl.SSLError):
                    pass
        return self.voidresp()


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

            # Wait for MQTT connection
            for _ in range(16):
                if printer.mqtt_client_ready:
                    break
                time.sleep(0.5)

            # Wait for printer to send its first status report (separate from MQTT connect)
            for _ in range(20):
                state_raw = str(printer.get_current_state())
                nozzle = printer.get_nozzle_temperature()
                if "UNKNOWN" not in state_raw.upper() and nozzle != 0.0:
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
    """Upload 3MF to printer /cache/ via implicit FTPS (port 990). Returns filename on printer."""
    filename = Path(path_3mf).name
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ftp = _ImplicitFTP_TLS(context=ctx)
    ftp.connect(host=BAMBU_IP, port=BAMBU_FTP_PORT, timeout=30)
    ftp.login(user="bblp", passwd=BAMBU_ACCESS_CODE)
    ftp.prot_p()  # protect data channel
    # /cache/ may not exist after an SD card reseat — create it if missing
    try:
        ftp.mkd("/cache")
        log.info("FTP: created /cache/ directory")
    except ftplib.error_perm:
        pass  # already exists
    with open(path_3mf, "rb") as f:
        ftp.storbinary(f"STOR /cache/{filename}", f)
    ftp.quit()
    log.info("FTP upload OK: /cache/%s", filename)
    return filename


# ── MQTT print trigger ────────────────────────────────────────────────────────

def _mqtt_print_trigger(filename: str, ams_slot: int = BAMBU_AMS_SLOT) -> None:
    """Send project_file command over MQTT to trigger the print job.

    ams_slot: AMS tray index (0-based globally). -1 = external spool, no AMS.
    """
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

    # Subscribe to report topic so we can log the printer's ack/rejection
    report_topic = f"device/{BAMBU_SERIAL}/report"
    client.subscribe(report_topic, qos=0)

    subtask = filename.replace(".3mf", "")
    use_ams = ams_slot >= 0
    # sequence_id must be unique per session — a static "0" is deduplicated
    # by the printer and silently ignored after the first message.
    seq_id = str(int(time.time() * 1000) % 100000)
    payload: dict = {
        "sequence_id": seq_id,
        "command": "project_file",
        "param": "Metadata/plate_1.gcode",
        "subtask_name": subtask,
        "url": f"ftp:///cache/{filename}",
        "task_id": "0",
        "subtask_id": "0",
        "profile_id": "0",
        "project_id": "0",
        "timelapse": False,
        "bed_leveling": True,
        "flow_cali": False,
        "vibration_cali": False,
        "layer_inspect": False,
        "use_ams": use_ams,
    }
    if use_ams:
        payload["ams_mapping"] = [ams_slot]
    msg = {"print": payload}
    topic = f"device/{BAMBU_SERIAL}/request"

    received: list[str] = []

    def _on_message(client, userdata, message):
        try:
            data = json.loads(message.payload)
            # Only log the print-command response, not periodic status pushes
            if "print" in data and "command" in data.get("print", {}):
                received.append(json.dumps(data["print"]))
        except Exception:
            pass

    client.on_message = _on_message

    result = client.publish(topic, json.dumps(msg), qos=1)
    result.wait_for_publish(timeout=10)
    # Give the printer time to respond and flush the send buffer
    time.sleep(2)
    client.loop_stop()
    client.disconnect()

    log.info("MQTT print trigger sent (seq=%s): %s → %s", seq_id, topic, filename)
    if received:
        log.info("Printer ack: %s", received[0])
    else:
        log.info("No ack received from printer within 2 s")


# ── Public async API ─────────────────────────────────────────────────────────

async def send_and_print(path_3mf: str, ams_slot: int = BAMBU_AMS_SLOT) -> dict:
    """
    Upload .3mf to printer /cache/ via FTPS, then trigger print via MQTT.
    Returns {status, filename, ams_slot}.
    """
    if not is_configured():
        raise RuntimeError(
            "Bambu printer not configured — set BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL"
        )
    loop = asyncio.get_running_loop()
    filename = await loop.run_in_executor(None, _ftp_upload, path_3mf)
    await loop.run_in_executor(None, _mqtt_print_trigger, filename, ams_slot)
    return {"status": "sent", "filename": filename, "ams_slot": ams_slot}
