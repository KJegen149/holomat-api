"""
Bambu Lab P1S — LAN-mode print dispatch with cloud auth for user_id.

Active path (LAN-only mode, Developer Mode ON, firmware 01.08.02):
  Auth:     BAMBU_EMAIL + BAMBU_PASSWORD → Bambu cloud → fetch user_id only
  Upload:   implicit FTPS port 990 → printer /cache/
  Trigger:  LAN MQTT project_file command (port 8883, file:///sdcard/cache/ URL)
  Auto-starts without touchscreen confirmation.
  Requires: BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL, BAMBU_EMAIL, BAMBU_PASSWORD

Cloud path (opt-in via BAMBU_USE_CLOUD=true — for printers not in LAN-only mode):
  Requires: BAMBU_EMAIL, BAMBU_PASSWORD, BAMBU_SERIAL
  See _cloud_send_and_print() and core/bambu_signing.py.
"""
import asyncio
import ftplib
import json
import os
import socket
import ssl
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger(__name__)

# ── Shared env vars ───────────────────────────────────────────────────────────
BAMBU_SERIAL      = os.getenv("BAMBU_SERIAL", "")

# ── Cloud-mode credentials (opt-in — see BAMBU_USE_CLOUD) ─────────────────────
BAMBU_EMAIL       = os.getenv("BAMBU_EMAIL", "")
BAMBU_PASSWORD    = os.getenv("BAMBU_PASSWORD", "")
BAMBU_TOKEN_FILE  = os.getenv("BAMBU_TOKEN_FILE", "scan_data/.bambu_token")
BAMBU_REGION      = os.getenv("BAMBU_REGION", "global")   # "global" or "china"
# Route prints through Bambu cloud. Off by default — the LAN path is used
# unless this is explicitly "true" (cloud is for printers not in LAN-only mode).
BAMBU_USE_CLOUD   = os.getenv("BAMBU_USE_CLOUD", "").strip().lower() == "true"

# ── LAN-mode credentials (default print path) ────────────────────────────────
BAMBU_IP          = os.getenv("BAMBU_IP", "")
BAMBU_ACCESS_CODE = os.getenv("BAMBU_ACCESS_CODE", "")
BAMBU_CERT        = os.getenv("BAMBU_CERT", "certs/printer.pem")
BAMBU_FTP_PORT    = int(os.getenv("BAMBU_FTP_PORT") or "990")
BAMBU_MQTT_PORT   = int(os.getenv("BAMBU_MQTT_PORT") or "8883")
BAMBU_AMS_SLOT    = int(os.getenv("BAMBU_AMS_SLOT") or "0")


def is_cloud_configured() -> bool:
    return bool(BAMBU_EMAIL and BAMBU_PASSWORD and BAMBU_SERIAL)


def is_lan_configured() -> bool:
    return bool(BAMBU_IP and BAMBU_ACCESS_CODE and BAMBU_SERIAL)


def is_configured() -> bool:
    return is_cloud_configured() or is_lan_configured()


# Serialises all printer-MQTT access — the P1S broker rejects new connections
# when the status poll and the print trigger try to connect at the same time.
_PRINTER_MQTT_LOCK = threading.Lock()
_LAST_STATUS: dict = {}


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
        global _LAST_STATUS
        if not _PRINTER_MQTT_LOCK.acquire(blocking=False):
            # a print dispatch holds the printer's MQTT — don't compete for it
            return _LAST_STATUS or {"state": "BUSY", "detail": "print dispatch in progress"}
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

            _LAST_STATUS = {
                "state": state,
                "nozzle_temp": printer.get_nozzle_temperature(),
                "bed_temp": printer.get_bed_temperature(),
                "progress": printer.get_percentage(),
                "current_file": current_file,
            }
            return _LAST_STATUS
        finally:
            try:
                printer.disconnect()
            except Exception:
                pass
            _PRINTER_MQTT_LOCK.release()

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
    """
    Upload 3MF to Bambu cloud S3, then dispatch via cloud MQTT.

    Cloud MQTT (us.mqtt.bambulab.com) relays the project_file command through
    Bambu's trusted infrastructure, which auto-starts the print on the printer
    without requiring touchscreen confirmation.
    """
    import requests as _requests
    import paho.mqtt.client as mqtt  # type: ignore
    client = _get_bambu_client()
    filename = Path(path_3mf).name

    # ── Step 1: Upload to S3 ─────────────────────────────────────────────────
    file_size = Path(path_3mf).stat().st_size
    log.info("Cloud: requesting upload URL for %s (%d bytes)", filename, file_size)
    upload_info = client.get_upload_url(filename=filename, size=file_size)

    upload_url: str = ""
    urls_array = upload_info.get("urls", [])
    size_url: str = ""
    for entry in urls_array:
        if isinstance(entry, dict):
            if entry.get("type") == "filename":
                upload_url = entry["url"]
            elif entry.get("type") == "size":
                size_url = entry["url"]
    if not upload_url:
        upload_url = upload_info.get("upload_url", "")
    if not upload_url:
        raise RuntimeError(f"No upload URL in Bambu response: {upload_info}")

    log.info("Cloud: uploading to S3 → %s", upload_url[:80] + "…")
    with open(path_3mf, "rb") as f:
        resp = _requests.put(upload_url, data=f, headers={}, timeout=120)
    if resp.status_code >= 400:
        raise RuntimeError(f"S3 upload failed ({resp.status_code}): {resp.text[:200]}")
    log.info("Cloud: S3 upload OK (HTTP %d)", resp.status_code)
    if size_url:
        try:
            _requests.put(size_url, data=str(file_size).encode(),
                          headers={"Content-Type": "text/plain"}, timeout=10)
        except Exception:
            pass

    # Permanent (unsigned) S3 URL — Bambu's cloud backend fetches the file from here
    permanent_url = upload_url.split("?")[0]
    log.info("Cloud: permanent_url=%s", permanent_url)

    # ── Step 2: Get user UID for cloud MQTT auth ─────────────────────────────
    user_info = client.get_user_info()
    uid = str(user_info.get("uid") or user_info.get("userId") or user_info.get("user_id", ""))
    if not uid:
        raise RuntimeError(f"Could not determine user UID from: {user_info}")
    log.info("Cloud: uid=%s", uid)

    # ── Step 3: Connect to cloud MQTT and send project_file ──────────────────
    CLOUD_BROKER = "us.mqtt.bambulab.com"
    CLOUD_PORT   = 8883

    # Retrieve the raw access token from the auth layer
    auth_obj = client._auth if hasattr(client, "_auth") else None
    access_token: str = ""
    if auth_obj and hasattr(auth_obj, "token"):
        access_token = auth_obj.token
    if not access_token and hasattr(client, "token"):
        access_token = client.token
    if not access_token and hasattr(client, "_token"):
        access_token = client._token
    if not access_token:
        # Last resort — re-read from token file
        token_path = Path(BAMBU_TOKEN_FILE)
        if token_path.exists():
            access_token = token_path.read_text().strip()
    if not access_token:
        raise RuntimeError("Could not retrieve access token for cloud MQTT")

    connected = False

    def _on_connect(mqttc, userdata, flags, *args):
        nonlocal connected
        rc = args[0] if args else 0
        connected = (rc == 0 if isinstance(rc, int) else rc.value == 0)

    try:
        mqttc = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined]
            client_id=f"holomat_{uuid.uuid4().hex[:8]}",
        )
    except AttributeError:
        mqttc = mqtt.Client(client_id=f"holomat_{uuid.uuid4().hex[:8]}")

    mqttc.on_connect = _on_connect
    mqtt_user = f"u_{uid}" if not uid.startswith("u_") else uid
    mqttc.username_pw_set(mqtt_user, access_token)
    mqttc.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)

    log.info("Cloud MQTT: connecting to %s:%d as %s", CLOUD_BROKER, CLOUD_PORT, mqtt_user)
    mqttc.connect(CLOUD_BROKER, CLOUD_PORT, keepalive=60)
    mqttc.loop_start()

    deadline = time.time() + 15
    while not connected and time.time() < deadline:
        time.sleep(0.1)
    if not connected:
        mqttc.loop_stop()
        raise RuntimeError("Cloud MQTT connect timed out after 15 s")

    from core.bambu_signing import sign_mqtt_payload
    subtask = filename.replace(".3mf", "")
    seq_id = str(int(time.time() * 1000) % 100000)
    print_cmd = {
        "sequence_id": seq_id,
        "command": "project_file",
        "param": "Metadata/plate_1.gcode",
        "subtask_name": subtask,
        "url": permanent_url,
        "timelapse": False,
        "bed_leveling": True,
        "flow_cali": False,
        "vibration_cali": False,
        "layer_inspect": False,
        "use_ams": False,
    }
    # Wrap in ACS signature — required by P1S firmware post-Jan 2025
    signed = sign_mqtt_payload(print_cmd, uid)
    topic = f"device/{BAMBU_SERIAL}/request"
    log.info("Cloud MQTT: publishing ACS-signed project_file → %s (cert=%s)", topic, signed["header"]["cert_id"])
    mqttc.publish(topic, json.dumps({"print": signed}), qos=0)
    time.sleep(1)
    mqttc.loop_stop()
    mqttc.disconnect()

    log.info("Cloud MQTT: print command sent (seq=%s)", seq_id)
    return {"filename": filename, "seq_id": seq_id, "cloud_status": "dispatched"}


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

def _mqtt_print_trigger(filename: str, ams_slot: int = BAMBU_AMS_SLOT,
                        user_id: str = "") -> None:
    """Send project_file command over LAN MQTT to trigger the print job."""
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

    # P1S expects file:///sdcard/cache/ — not ftp:// — to reference the uploaded file.
    # user_id must match the Bambu account linked to the printer; without it the
    # printer accepts the command (result:success) then immediately aborts the job.
    use_ams = ams_slot >= 0 and BAMBU_AMS_SLOT >= 0
    inner: dict = {
        "sequence_id": seq_id,
        "command": "project_file",
        "param": "Metadata/plate_1.gcode",
        "subtask_name": subtask,
        "url": f"file:///sdcard/cache/{filename}",
        "file": filename,
        "md5": "",
        "project_id": "0",
        "profile_id": "0",
        "task_id": "0",
        "subtask_id": "0",
        "bed_type": "auto",
        "timelapse": False,
        "bed_leveling": True,
        "flow_cali": True,
        "vibration_cali": True,
        "layer_inspect": True,
        "use_ams": use_ams,
        "ams_mapping": [ams_slot] if use_ams else [],
    }
    if user_id:
        inner["user_id"] = user_id
    msg = {"print": inner}
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
    time.sleep(2)
    client.loop_stop()
    client.disconnect()

    log.info("MQTT print trigger sent (seq=%s): %s → %s", seq_id, topic, filename)
    if received:
        log.info("Printer ack: %s", received[0])
    else:
        log.info("No ack received from printer within 2 s")


def _get_user_id() -> str:
    """Fetch the Bambu account user_id via cloud auth. Returns empty string on failure."""
    if not is_cloud_configured():
        return ""
    try:
        client = _get_bambu_client()
        user_info = client.get_user_info()
        uid = str(user_info.get("uid") or user_info.get("userId")
                  or user_info.get("user_id", ""))
        if uid:
            log.info("Cloud auth: user_id=%s", uid)
        return uid
    except Exception as e:
        log.warning("Could not fetch user_id from cloud auth: %s", e)
        return ""


def _lan_send_and_print(path_3mf: str, ams_slot: int = BAMBU_AMS_SLOT) -> dict:
    """LAN mode: FTP upload + MQTT trigger with cloud-authenticated user_id."""
    uid = _get_user_id()
    if not uid:
        log.warning("No user_id available — printer may abort job immediately. "
                    "Set BAMBU_EMAIL + BAMBU_PASSWORD to authenticate.")
    filename = _ftp_upload(path_3mf)
    # Hold the printer-MQTT lock so a concurrent status poll cannot occupy the
    # P1S broker while we connect to send the print command.
    with _PRINTER_MQTT_LOCK:
        _mqtt_print_trigger(filename, ams_slot=ams_slot, user_id=uid)
    return {"filename": filename, "ams_slot": ams_slot, "user_id": uid}


# ── Public async API ──────────────────────────────────────────────────────────

async def send_and_print(path_3mf: str, ams_slot: int = BAMBU_AMS_SLOT) -> dict:
    """
    Upload the .3mf and start the print.

    Default path is LAN (FTPS upload + LAN MQTT project_file). With a valid
    user_id the printer auto-starts the job — no touchscreen confirmation.
    The cloud path is opt-in via BAMBU_USE_CLOUD=true, preserved for printers
    that are not in LAN-only mode (see _cloud_send_and_print).
    Returns {status, mode, ...}.
    """
    loop = asyncio.get_running_loop()

    if BAMBU_USE_CLOUD and is_cloud_configured():
        log.info("Using cloud mode for print dispatch (BAMBU_USE_CLOUD=true)")
        result = await loop.run_in_executor(None, _cloud_send_and_print, path_3mf)
        return {"status": "sent", "mode": "cloud", **result}

    if not is_lan_configured():
        raise RuntimeError(
            "Bambu printer not configured for LAN — set BAMBU_IP, BAMBU_ACCESS_CODE "
            "and BAMBU_SERIAL (plus BAMBU_EMAIL+BAMBU_PASSWORD for auto-start), or "
            "set BAMBU_USE_CLOUD=true with cloud credentials"
        )

    log.info("Using LAN mode for print dispatch")
    result = await loop.run_in_executor(None, _lan_send_and_print, path_3mf, ams_slot)
    return {"status": "sent", "mode": "lan", **result}
