"""
Bambu Lab P1S — cloud-first print dispatch with LAN fallback.

Cloud mode (preferred, auto-starts print):
  Auth:     bambu-lab-cloud-api  → Bambu cloud REST API
  Upload:   POST to Bambu S3 via signed URL
  Trigger:  POST /v1/iot-service/api/user/print  (auto-starts, no touchscreen)
  Requires: BAMBU_EMAIL, BAMBU_PASSWORD, BAMBU_SERIAL

LAN fallback (manual touchscreen confirmation required):
  Upload:   ftplib implicit FTPS → printer /cache/ (port 990)
  Trigger:  paho-mqtt project_file command (port 8883)
  Requires: BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL
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

# ── Shared env vars ───────────────────────────────────────────────────────────
BAMBU_SERIAL      = os.getenv("BAMBU_SERIAL", "")

# ── Cloud-mode credentials ────────────────────────────────────────────────────
BAMBU_EMAIL       = os.getenv("BAMBU_EMAIL", "")
BAMBU_PASSWORD    = os.getenv("BAMBU_PASSWORD", "")
BAMBU_TOKEN_FILE  = os.getenv("BAMBU_TOKEN_FILE", "scan_data/.bambu_token")
BAMBU_REGION      = os.getenv("BAMBU_REGION", "global")   # "global" or "china"

# ── LAN-mode credentials (fallback) ──────────────────────────────────────────
BAMBU_IP          = os.getenv("BAMBU_IP", "")
BAMBU_ACCESS_CODE = os.getenv("BAMBU_ACCESS_CODE", "")
BAMBU_CERT        = os.getenv("BAMBU_CERT", "certs/printer.pem")
BAMBU_FTP_PORT    = int(os.getenv("BAMBU_FTP_PORT", "990"))
BAMBU_MQTT_PORT   = int(os.getenv("BAMBU_MQTT_PORT", "8883"))
BAMBU_AMS_SLOT    = int(os.getenv("BAMBU_AMS_SLOT", "0"))


def is_cloud_configured() -> bool:
    return bool(BAMBU_EMAIL and BAMBU_PASSWORD and BAMBU_SERIAL)


def is_lan_configured() -> bool:
    return bool(BAMBU_IP and BAMBU_ACCESS_CODE and BAMBU_SERIAL)


def is_configured() -> bool:
    return is_cloud_configured() or is_lan_configured()


# ── Status (LAN MQTT) ─────────────────────────────────────────────────────────

async def get_status() -> dict:
    """
    Connect to printer via LAN MQTT, wait for a status push, return state dict.
    Returns {state, nozzle_temp, bed_temp, progress, current_file}.
    Requires LAN credentials (BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL).
    """
    try:
        import bambulabs_api as bl  # type: ignore
    except ImportError:
        return {"error": "bambulabs-api not installed"}

    if not is_lan_configured():
        return {"error": "Bambu LAN credentials not configured (BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL)"}

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

            for _ in range(20):
                state_raw = str(printer.get_current_state())
                nozzle = printer.get_nozzle_temperature()
                if "UNKNOWN" not in state_raw.upper() and nozzle != 0.0:
                    break
                time.sleep(0.5)

            state = str(printer.get_current_state())
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


# ── Cloud upload + print trigger ──────────────────────────────────────────────

def _get_bambu_client():
    """Authenticate with Bambu cloud and return a BambuClient."""
    from bambulab import BambuAuthenticator, BambuClient  # type: ignore
    Path(BAMBU_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
    auth = BambuAuthenticator(region=BAMBU_REGION, token_file=BAMBU_TOKEN_FILE)
    token = auth.get_or_create_token(username=BAMBU_EMAIL, password=BAMBU_PASSWORD)
    return BambuClient(token=token)


def _cloud_send_and_print(path_3mf: str) -> dict:
    """Upload 3MF to Bambu cloud S3 and dispatch print job. Auto-starts on printer."""
    client = _get_bambu_client()
    log.info("Cloud: uploading %s", path_3mf)
    upload = client.upload_file(file_path=path_3mf)
    filename = upload["filename"]
    # upload_url is the S3 pre-signed PUT URL — also usable as the file_url for
    # start_print_job since it's valid for ~1 hour and Bambu's service fetches from it.
    file_url = upload.get("upload_url") or upload.get("file_url")
    log.info("Cloud: upload OK → %s  url=%s", filename, file_url)

    log.info("Cloud: dispatching print job to %s", BAMBU_SERIAL)
    # Use start_print_job directly — start_cloud_print searches the cloud file
    # index which is not populated by upload_file's direct S3 PUT path.
    job = client.start_print_job(
        device_id=BAMBU_SERIAL,
        file_name=filename,
        file_url=file_url,
    )
    log.info("Cloud: print dispatched — job_id=%s status=%s", job.get("job_id"), job.get("status"))
    return {"filename": filename, "job_id": job.get("job_id"), "cloud_status": job.get("status")}


# ── LAN FTP upload ────────────────────────────────────────────────────────────

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


def _ftp_upload(path_3mf: str) -> str:
    """Upload 3MF to printer /cache/ via implicit FTPS (port 990). Returns filename on printer."""
    filename = Path(path_3mf).name
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ftp = _ImplicitFTP_TLS(context=ctx)
    ftp.connect(host=BAMBU_IP, port=BAMBU_FTP_PORT, timeout=30)
    ftp.login(user="bblp", passwd=BAMBU_ACCESS_CODE)
    ftp.prot_p()
    try:
        ftp.mkd("/cache")
        log.info("FTP: created /cache/ directory")
    except ftplib.error_perm:
        pass
    with open(path_3mf, "rb") as f:
        ftp.storbinary(f"STOR /cache/{filename}", f)
    ftp.quit()
    log.info("FTP upload OK: /cache/%s", filename)
    return filename


# ── LAN MQTT print trigger ────────────────────────────────────────────────────

def _mqtt_print_trigger(filename: str, ams_slot: int = BAMBU_AMS_SLOT) -> None:
    """Send project_file command over MQTT to trigger the print job (requires touchscreen confirmation)."""
    try:
        import paho.mqtt.client as mqtt  # type: ignore
    except ImportError:
        raise RuntimeError("paho-mqtt not installed — pip install paho-mqtt")

    connected = False

    def _on_connect(client, userdata, flags, *args):
        nonlocal connected
        rc = args[0] if args else 0
        connected = (rc == 0 if isinstance(rc, int) else rc.value == 0)

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

    report_topic = f"device/{BAMBU_SERIAL}/report"
    client.subscribe(report_topic, qos=0)

    subtask = filename.replace(".3mf", "")
    seq_id = str(int(time.time() * 1000) % 100000)
    msg = {
        "print": {
            "sequence_id": seq_id,
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

    received: list[str] = []

    def _on_message(client, userdata, message):
        try:
            data = json.loads(message.payload)
            if "print" in data and "command" in data.get("print", {}):
                received.append(json.dumps(data["print"]))
        except Exception:
            pass

    client.on_message = _on_message

    client.publish(topic, json.dumps(msg), qos=0)
    time.sleep(1)
    client.loop_stop()
    client.disconnect()

    log.info("MQTT print trigger sent (seq=%s): %s → %s", seq_id, topic, filename)
    if received:
        log.info("Printer ack: %s", received[0])
    else:
        log.info("No ack received from printer within 1 s")


def _lan_send_and_print(path_3mf: str, ams_slot: int = BAMBU_AMS_SLOT) -> dict:
    """LAN fallback: FTP upload + MQTT trigger. Requires touchscreen confirmation."""
    filename = _ftp_upload(path_3mf)
    _mqtt_print_trigger(filename, ams_slot=ams_slot)
    return {"filename": filename, "ams_slot": ams_slot}


# ── Public async API ──────────────────────────────────────────────────────────

async def send_and_print(path_3mf: str, ams_slot: int = BAMBU_AMS_SLOT) -> dict:
    """
    Upload .3mf and trigger print.

    Prefers cloud mode (BAMBU_EMAIL + BAMBU_PASSWORD) which auto-starts the print.
    Falls back to LAN mode (BAMBU_IP + BAMBU_ACCESS_CODE) which requires touchscreen confirmation.
    Returns {status, filename, mode, ...}.
    """
    if not is_configured():
        raise RuntimeError(
            "Bambu printer not configured — set BAMBU_EMAIL+BAMBU_PASSWORD+BAMBU_SERIAL "
            "for cloud mode, or BAMBU_IP+BAMBU_ACCESS_CODE+BAMBU_SERIAL for LAN mode"
        )

    loop = asyncio.get_running_loop()

    if is_cloud_configured():
        log.info("Using cloud mode for print dispatch (auto-start, no confirmation required)")
        result = await loop.run_in_executor(None, _cloud_send_and_print, path_3mf)
        return {"status": "sent", "mode": "cloud", **result}

    log.info("Using LAN mode for print dispatch (touchscreen confirmation required)")
    result = await loop.run_in_executor(None, _lan_send_and_print, path_3mf, ams_slot)
    return {"status": "sent", "mode": "lan", **result}
