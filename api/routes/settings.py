"""Settings API routes."""
import asyncio
import os
import re
import secrets
import socket
import threading
from pathlib import Path
from urllib import request as urllib_req, error as urllib_err
from urllib.parse import urlparse

from dotenv import dotenv_values
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

ENV_FILE = Path(__file__).parent.parent.parent / ".env"

# Admin gate: when HOLOMAT_ADMIN_KEY is set, every /api/settings request must
# carry a matching X-Admin-Key header. When unset the gate is open (so an
# unconfigured install is not locked out) — set the key to require auth.
_ADMIN_KEY = os.getenv("HOLOMAT_ADMIN_KEY", "")

# Guards .env read-modify-write so concurrent saves cannot interleave
_ENV_LOCK = threading.Lock()

# A valid environment-variable name
_VALID_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _require_admin(x_admin_key: str = Header(default="")) -> None:
    """Router-wide gate for the Settings API."""
    if not _ADMIN_KEY:
        return
    if not secrets.compare_digest(x_admin_key, _ADMIN_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")


router = APIRouter(tags=["settings"], dependencies=[Depends(_require_admin)])

SENSITIVE_KEYS = {
    "BAMBU_PASSWORD",
    "BAMBU_ACCESS_CODE",
    "GEMINI_API_KEY",
    "CF_API_KEY",
    "HA_MQTT_PASS",
    "HA_TOKEN",
}

MASK = "••••••"

KNOWN_KEYS = [
    "BAMBU_SERIAL",
    "BAMBU_EMAIL",
    "BAMBU_PASSWORD",
    "BAMBU_REGION",
    "BAMBU_IP",
    "BAMBU_ACCESS_CODE",
    "BAMBU_AMS_SLOT",
    "BAMBU_CERT",
    "HA_URL",
    "HA_MQTT_HOST",
    "HA_MQTT_PORT",
    "HA_MQTT_USER",
    "HA_MQTT_PASS",
    "HA_TOKEN",
    "CF_API_URL",
    "CF_API_KEY",
    "ORCA_CLI",
    "OPENSCAD_BIN",
    "CAMERA_DEVICE",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "WYOMING_ENABLED",
    "WYOMING_STT_PORT",
    "WYOMING_TTS_PORT",
    "WYOMING_STT_URL",
    "WYOMING_TTS_URL",
    "WYOMING_LLM_URL",
    "WYOMING_MIC_INDEX",
    "WYOMING_SPEAKER_INDEX",
    "WYOMING_WAKE_SENSITIVITY",
]


def _read_env() -> dict[str, str]:
    """Parse .env via python-dotenv — the same loader main.py uses at startup,
    so `export `, inline comments and quoting are handled consistently."""
    if not ENV_FILE.exists():
        return {}
    return {k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None}


def _env_quote(val: str) -> str:
    """Double-quote and escape a value for safe .env round-tripping."""
    escaped = (
        val.replace("\\", "\\\\")
           .replace('"', '\\"')
           .replace("\n", "\\n")
           .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _write_env(data: dict[str, str]) -> None:
    """Atomically write .env. Values are quoted/escaped (no newline injection),
    and only non-empty values are written so systemd defaults aren't stomped."""
    lines: list[str] = []
    written: set[str] = set()
    for key in KNOWN_KEYS:
        val = data.get(key, "")
        if val:
            lines.append(f"{key}={_env_quote(val)}\n")
        written.add(key)
    for key, val in data.items():
        if key not in written and val and _VALID_KEY.match(key):
            lines.append(f"{key}={_env_quote(val)}\n")
    tmp = ENV_FILE.with_name(ENV_FILE.name + ".tmp")
    tmp.write_text("".join(lines))
    tmp.replace(ENV_FILE)


def _resolve(key: str, env_file: dict[str, str]) -> str:
    """Return value from .env file first, then fall back to process env (systemd)."""
    return env_file.get(key) or os.getenv(key, "")


# ── GET /api/settings ────────────────────────────────────────────────────────

@router.get("")
async def get_settings():
    raw = _read_env()
    # For display: merge .env over process env so UI reflects what's actually active
    result: dict[str, str] = {}
    for key in KNOWN_KEYS:
        val = _resolve(key, raw)
        result[key] = MASK if (key in SENSITIVE_KEYS and val) else val
    return {
        "settings": result,
        "env_file_exists": ENV_FILE.exists(),
        "auth_enabled": bool(_ADMIN_KEY),
    }


# ── POST /api/settings ───────────────────────────────────────────────────────

class SettingsBody(BaseModel):
    settings: dict[str, str]


@router.post("")
async def save_settings(body: SettingsBody):
    with _ENV_LOCK:
        raw = _read_env()
        for key, value in body.settings.items():
            if key not in KNOWN_KEYS:
                continue
            if key in SENSITIVE_KEYS:
                if value and value != MASK:
                    raw[key] = value
            else:
                raw[key] = value
        _write_env(raw)
    return {"saved": True, "restart_required": True}


# ── POST /api/settings/restart ───────────────────────────────────────────────

@router.post("/restart")
async def restart_service():
    """Exit with code 1 so systemd (Restart=on-failure) restarts the process."""
    import threading, time
    def _exit():
        time.sleep(0.5)
        os._exit(1)  # non-zero triggers Restart=on-failure
    threading.Thread(target=_exit, daemon=True).start()
    return {"restarting": True}


# ── GET /api/settings/test ───────────────────────────────────────────────────

async def _tcp(host: str, port: int) -> dict:
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: socket.create_connection((host, port), timeout=3).close()
        )
        return {"ok": True, "detail": f"{host}:{port} reachable"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


async def _http(url: str, headers: dict) -> dict:
    try:
        loop = asyncio.get_running_loop()
        def _do():
            req = urllib_req.Request(url, headers=headers)
            try:
                with urllib_req.urlopen(req, timeout=5) as r:
                    return r.status
            except urllib_err.HTTPError as e:
                return e.code
        status = await loop.run_in_executor(None, _do)
        return {"ok": status < 500, "detail": f"HTTP {status}"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


@router.get("/test")
async def test_connections():
    env = _read_env()

    async def _gemini() -> dict:
        key = _resolve("GEMINI_API_KEY", env)
        if not key:
            return {"ok": False, "detail": "GEMINI_API_KEY not set"}
        try:
            import google.generativeai as genai
            loop = asyncio.get_running_loop()
            genai.configure(api_key=key)
            models = await loop.run_in_executor(None, lambda: list(genai.list_models()))
            return {"ok": True, "detail": f"{len(models)} models available"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}

    async def _cloudflare() -> dict:
        url = _resolve("CF_API_URL", env)
        key = _resolve("CF_API_KEY", env)
        if not url:
            return {"ok": False, "detail": "CF_API_URL not set"}
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        parsed = urlparse(url)
        port = 443 if parsed.scheme == "https" else 80
        tcp = await _tcp(parsed.hostname or "", port)
        if not tcp["ok"]:
            return tcp
        if not key:
            return {"ok": False, "detail": "Worker reachable but CF_API_KEY not set"}
        return {"ok": True, "detail": "Worker reachable, key set"}

    async def _ha_token() -> dict:
        url = _resolve("HA_URL", env)
        token = _resolve("HA_TOKEN", env)
        if not url:
            return {"ok": False, "detail": "HA_URL not set"}
        if not token:
            return {"ok": False, "detail": "HA_TOKEN not set"}
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return await _http(f"{url.rstrip('/')}/api/", {"Authorization": f"Bearer {token}"})

    async def _ha_mqtt() -> dict:
        host = _resolve("HA_MQTT_HOST", env)
        if not host:
            return {"ok": False, "detail": "HA_MQTT_HOST not set"}
        port = int(_resolve("HA_MQTT_PORT", env) or "1883")
        return await _tcp(host, port)

    async def _bambu() -> dict:
        ip = _resolve("BAMBU_IP", env)
        if not ip:
            return {"ok": False, "detail": "BAMBU_IP not set"}
        return await _tcp(ip, 8883)

    results = await asyncio.gather(
        _gemini(), _cloudflare(), _ha_token(), _ha_mqtt(), _bambu(),
        return_exceptions=True,
    )
    labels = ["gemini", "cloudflare", "ha_token", "ha_mqtt", "bambu_lan"]
    return {
        "results": {
            label: r if isinstance(r, dict) else {"ok": False, "detail": str(r)}
            for label, r in zip(labels, results)
        }
    }


@router.get("/test/meshy")
async def test_meshy():
    """Probe the Meshy API via the Cloudflare worker."""
    import httpx
    env = _read_env()
    cf_url = _resolve("CF_API_URL", env).rstrip("/")
    cf_key = _resolve("CF_API_KEY", env)

    if not cf_url:
        return {"ok": False, "detail": "CF_API_URL not set"}
    if not cf_key:
        return {"ok": False, "detail": "CF_API_KEY not set — cannot authenticate with Meshy"}

    probe_url = f"{cf_url}/api/meshy/balance"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(probe_url, headers={"X-API-Key": cf_key})
        status = r.status_code
        try:
            body = r.json()
        except Exception:
            body = {}
        if status in (401, 403):
            return {"ok": False, "detail": f"HTTP {status} — CF_API_KEY rejected by worker"}
        if status == 500 and "not configured" in str(body.get("error", "")):
            return {"ok": False, "detail": "MESHY_API_KEY not set in Cloudflare Worker secrets"}
        if status < 500:
            credits = body.get("credit_balance") or body.get("balance") or body.get("credits")
            detail = f"Meshy authenticated — balance: {credits}" if credits is not None else f"Meshy reachable (HTTP {status})"
            return {"ok": True, "detail": detail}
        return {"ok": False, "detail": f"HTTP {status} — {body.get('error', 'worker error')}"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}




@router.get("/test/bambu")
async def test_bambu_dry_run():
    """
    Full Bambu dry run — no file upload, no print trigger.
    Tests: FTPS login, cloud auth (user_id), live MQTT status poll.
    May take up to 30 s (MQTT status poll retries).
    """
    import ssl
    env = _read_env()
    ip           = _resolve("BAMBU_IP", env)
    access_code  = _resolve("BAMBU_ACCESS_CODE", env)
    serial       = _resolve("BAMBU_SERIAL", env)
    email        = _resolve("BAMBU_EMAIL", env)
    password     = _resolve("BAMBU_PASSWORD", env)
    region       = _resolve("BAMBU_REGION", env) or "global"
    token_file   = _resolve("BAMBU_TOKEN_FILE", env) or "scan_data/.bambu_token"
    ftp_port     = int(_resolve("BAMBU_FTP_PORT", env) or "990")
    mqtt_port    = int(_resolve("BAMBU_MQTT_PORT", env) or "8883")

    loop = asyncio.get_running_loop()

    # ── Step 1: FTPS login ────────────────────────────────────────────────────
    async def _ftps_login() -> dict:
        if not ip or not access_code:
            return {"ok": False, "detail": "BAMBU_IP or BAMBU_ACCESS_CODE not set"}
        def _do():
            from core.printer import _ImplicitFTP_TLS
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ftp = _ImplicitFTP_TLS(context=ctx)
            ftp.connect(host=ip, port=ftp_port, timeout=10)
            ftp.login(user="bblp", passwd=access_code)
            ftp.prot_p()
            try:
                files = ftp.nlst("/cache")
            except Exception:
                files = []
            ftp.quit()
            return len(files)
        try:
            n = await loop.run_in_executor(None, _do)
            return {"ok": True, "detail": f"FTPS login OK — /cache has {n} file(s)"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}

    # ── Step 2: Cloud auth (user_id) ─────────────────────────────────────────
    async def _cloud_auth() -> dict:
        if not email or not password:
            return {"ok": False, "detail": "BAMBU_EMAIL or BAMBU_PASSWORD not set"}
        def _do():
            from bambulab import BambuAuthenticator, BambuClient  # type: ignore
            Path(token_file).parent.mkdir(parents=True, exist_ok=True)
            auth = BambuAuthenticator(region=region, token_file=token_file)
            token = auth.get_or_create_token(username=email, password=password)
            client = BambuClient(token=token)
            info = client.get_user_info()
            uid = str(info.get("uid") or info.get("userId") or info.get("user_id", ""))
            return uid
        try:
            uid = await loop.run_in_executor(None, _do)
            if uid:
                return {"ok": True, "detail": f"Authenticated — user_id={uid}"}
            return {"ok": False, "detail": "Auth succeeded but no user_id returned"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}

    # ── Step 3: MQTT status poll ──────────────────────────────────────────────
    async def _mqtt_status() -> dict:
        if not ip or not access_code or not serial:
            return {"ok": False, "detail": "BAMBU_IP, BAMBU_ACCESS_CODE, or BAMBU_SERIAL not set"}
        try:
            from core.printer import get_status
            result = await get_status()
            if "error" in result:
                return {"ok": False, "detail": result["error"]}
            state = result.get("state", "unknown")
            nozzle = result.get("nozzle_temp", 0)
            bed = result.get("bed_temp", 0)
            return {"ok": True, "detail": f"State={state}, nozzle={nozzle}°C, bed={bed}°C"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}

    r1, r2, r3 = await asyncio.gather(
        _ftps_login(), _cloud_auth(), _mqtt_status(),
        return_exceptions=True,
    )
    def _wrap(r):
        return r if isinstance(r, dict) else {"ok": False, "detail": str(r)}
    return {
        "results": {
            "ftps_login":  _wrap(r1),
            "cloud_auth":  _wrap(r2),
            "mqtt_status": _wrap(r3),
        }
    }


# ── POST /api/settings/bambu-auth ────────────────────────────────────────────

class BambuAuthBody(BaseModel):
    otp: str = ""


@router.post("/bambu-auth")
async def bambu_cloud_auth(body: BambuAuthBody):
    """Authenticate with Bambu cloud, optionally with an OTP code, and cache the token."""
    env = _read_env()
    email      = _resolve("BAMBU_EMAIL", env)
    password   = _resolve("BAMBU_PASSWORD", env)
    region     = _resolve("BAMBU_REGION", env) or "global"
    token_file = _resolve("BAMBU_TOKEN_FILE", env) or "scan_data/.bambu_token"

    if not email or not password:
        raise HTTPException(400, "BAMBU_EMAIL and BAMBU_PASSWORD must be set first")

    loop = asyncio.get_running_loop()

    def _do():
        from bambulab import BambuAuthenticator, BambuClient  # type: ignore
        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        auth = BambuAuthenticator(region=region, token_file=token_file)
        otp = body.otp.strip() or None
        try:
            token = auth.get_or_create_token(username=email, password=password, otp=otp)
        except TypeError:
            token = auth.get_or_create_token(username=email, password=password)
        client = BambuClient(token=token)
        info = client.get_user_info()
        uid = str(info.get("uid") or info.get("userId") or info.get("user_id", ""))
        return uid

    try:
        uid = await loop.run_in_executor(None, _do)
        ok = bool(uid)
        return {"ok": ok, "user_id": uid, "detail": f"Authenticated — user_id={uid}" if ok else "No user_id in response"}
    except Exception as e:
        return {"ok": False, "user_id": "", "detail": str(e)}
