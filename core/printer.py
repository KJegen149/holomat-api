"""
Bambu Lab P1S — LAN-mode print dispatch with cloud auth for user_id.

Verified working on firmware 01.08.00 and 01.08.02 with Developer Mode ON.
The printer can stay cloud-connected (Bambu Handy / Studio keep working) —
LAN-only mode is NOT required.

  Auth:     BAMBU_EMAIL + BAMBU_PASSWORD → Bambu cloud → fetch user_id only
  Upload:   implicit FTPS port 990 → printer /cache/
  Trigger:  LAN MQTT project_file command (port 8883, file:///sdcard/cache/ URL)

Required env: BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL, BAMBU_EMAIL, BAMBU_PASSWORD
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

# ── Env vars ──────────────────────────────────────────────────────────────────
BAMBU_SERIAL      = os.getenv("BAMBU_SERIAL", "")
BAMBU_IP          = os.getenv("BAMBU_IP", "")
BAMBU_ACCESS_CODE = os.getenv("BAMBU_ACCESS_CODE", "")
BAMBU_CERT        = os.getenv("BAMBU_CERT", "certs/printer.pem")
BAMBU_FTP_PORT    = int(os.getenv("BAMBU_FTP_PORT") or "990")
BAMBU_MQTT_PORT   = int(os.getenv("BAMBU_MQTT_PORT") or "8883")
BAMBU_AMS_SLOT    = int(os.getenv("BAMBU_AMS_SLOT") or "0")

# Cloud auth (needed only to look up user_id, which the LAN MQTT payload requires).
BAMBU_EMAIL       = os.getenv("BAMBU_EMAIL", "")
BAMBU_PASSWORD    = os.getenv("BAMBU_PASSWORD", "")
BAMBU_TOKEN_FILE  = os.getenv("BAMBU_TOKEN_FILE", "scan_data/.bambu_token")
BAMBU_REGION      = os.getenv("BAMBU_REGION", "global")   # "global" or "china"


class PrinterAuthError(RuntimeError):
    """Raised when printer-side auth or Bambu cloud auth fails in a way the user can fix.

    These messages are surfaced verbatim in the Print tab's failed-job error field,
    so they need to read like instructions, not stack traces.
    """


def is_cloud_configured() -> bool:
    """True iff we can reach Bambu cloud to look up the user_id."""
    return bool(BAMBU_EMAIL and BAMBU_PASSWORD and BAMBU_SERIAL)


def is_lan_configured() -> bool:
    return bool(BAMBU_IP and BAMBU_ACCESS_CODE and BAMBU_SERIAL)


def is_configured() -> bool:
    return is_lan_configured()


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


# ── Bambu cloud auth (for user_id lookup only) ────────────────────────────────

def _get_bambu_client():
    """Authenticate with Bambu cloud and return a BambuClient (for user_id lookup)."""
    from bambulab import BambuAuthenticator, BambuClient  # type: ignore
    Path(BAMBU_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
    auth = BambuAuthenticator(region=BAMBU_REGION, token_file=BAMBU_TOKEN_FILE)
    token = auth.get_or_create_token(username=BAMBU_EMAIL, password=BAMBU_PASSWORD)
    return BambuClient(token=token)


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
    connect_rc: Optional[int] = None  # captured for clearer error messages on failure

    def _on_connect(client, userdata, flags, *args):
        nonlocal connected, connect_rc
        rc = args[0] if args else 0
        rc_int = rc if isinstance(rc, int) else getattr(rc, "value", -1)
        connect_rc = rc_int
        connected = (rc_int == 0)

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
        # paho rc 4 = bad username/password, rc 5 = not authorized. For Bambu the
        # MQTT password IS the access code, so both mean "the access code we have
        # is wrong" — which most often means the code rotated on the printer.
        if connect_rc in (4, 5):
            raise PrinterAuthError(
                f"Printer rejected the access code (MQTT rc={connect_rc}). "
                "The BAMBU_ACCESS_CODE has likely rotated — check Settings → Network "
                "on the printer touchscreen and update it under Holomat Settings → "
                "Bambu Printer → Access Code."
            )
        raise RuntimeError(
            f"MQTT connect to printer timed out after 10 s (rc={connect_rc}). "
            f"Check that the printer is on, on the LAN, and reachable at {BAMBU_IP}:{BAMBU_MQTT_PORT}."
        )

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

    msgs: list[dict] = []

    def _on_message(client, userdata, message):
        try:
            data = json.loads(message.payload)
            p = data.get("print")
            if isinstance(p, dict):
                msgs.append(p)
        except Exception:
            pass

    client.on_message = _on_message

    client.publish(topic, json.dumps(msg), qos=0)

    # Wait for the printer's verdict on the project_file command. It echoes a
    # message with command="project_file" carrying a result/reason; capture it
    # so we know whether the print was accepted, rejected, or silently ignored.
    project_resp = None
    deadline = time.time() + 8
    while time.time() < deadline and project_resp is None:
        project_resp = next((p for p in msgs if p.get("command") == "project_file"), None)
        time.sleep(0.2)

    client.loop_stop()
    client.disconnect()

    log.info("MQTT print trigger sent (seq=%s): %s → %s", seq_id, topic, filename)
    if project_resp is not None:
        log.info("Printer project_file response: %s", json.dumps(project_resp))
    else:
        log.warning("No project_file response in 8 s — printer did not acknowledge the command.")
        status = [p for p in msgs if p.get("command") == "push_status"]
        if status:
            keys = ("gcode_state", "mc_print_stage", "print_error", "print_type",
                    "fail_reason", "mc_percent", "subtask_name", "print_gcode_action")
            snap = {k: status[-1][k] for k in keys if k in status[-1]}
            log.warning("Printer status after trigger: %s", json.dumps(snap))


_OTP_HINTS = ("otp", "verification code", "verification_code", "two-factor",
              "two factor", "2fa", "mfa", "auth_code", "needs_verify")


def _get_user_id() -> str:
    """Fetch the Bambu account user_id via cloud auth. Returns empty string on
    soft failures; raises PrinterAuthError when the user must take action
    (e.g. complete an OTP challenge in Bambu Handy).
    """
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
        msg = str(e).lower()
        if any(hint in msg for hint in _OTP_HINTS):
            raise PrinterAuthError(
                "Bambu cloud needs an OTP verification before it will return a "
                "user_id. Open Bambu Handy, complete the verification challenge, "
                "then queue the print again."
            ) from e
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
    Upload the .3mf and start the print over LAN.

    FTPS upload + LAN MQTT project_file command. With a valid user_id the
    printer auto-starts the job — no touchscreen confirmation needed.
    Returns {status, mode, filename, ams_slot, user_id}.
    """
    if not is_lan_configured():
        raise RuntimeError(
            "Bambu printer not configured — set BAMBU_IP, BAMBU_ACCESS_CODE, "
            "BAMBU_SERIAL (and BAMBU_EMAIL + BAMBU_PASSWORD so the printer auto-starts)"
        )

    log.info("Using LAN mode for print dispatch")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _lan_send_and_print, path_3mf, ams_slot)
    return {"status": "sent", "mode": "lan", **result}
