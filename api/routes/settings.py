"""Settings API routes — Phase 9."""
import asyncio
import os
import socket
from pathlib import Path
from urllib import request as urllib_req, error as urllib_err
from urllib.parse import urlparse
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["settings"])

ENV_FILE = Path(__file__).parent.parent.parent / ".env"

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
    """Parse .env file without inheriting the process environment."""
    if not ENV_FILE.exists():
        return {}
    result: dict[str, str] = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env(data: dict[str, str]) -> None:
    """Write dict to .env; only non-empty values are written so systemd defaults aren't stomped."""
    lines: list[str] = []
    written: set[str] = set()
    for key in KNOWN_KEYS:
        val = data.get(key, "")
        if val:
            lines.append(f"{key}={val}\n")
        written.add(key)
    for key, val in data.items():
        if key not in written and val:
            lines.append(f"{key}={val}\n")
    ENV_FILE.write_text("".join(lines))


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
    return {"settings": result, "env_file_exists": ENV_FILE.exists()}


# ── POST /api/settings ───────────────────────────────────────────────────────

class SettingsBody(BaseModel):
    settings: dict[str, str]


@router.post("")
async def save_settings(body: SettingsBody):
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
        return {"ok": True, "detail": f"Worker reachable, key set"}

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
