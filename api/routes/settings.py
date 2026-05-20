"""Settings API routes — Phase 9."""
from pathlib import Path
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

# Ordered list of all managed keys
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
    """Parse .env file into a dict without inheriting the process environment."""
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
    """Write dict back to .env, preserving unknown keys at the end."""
    lines: list[str] = []
    written: set[str] = set()
    for key in KNOWN_KEYS:
        val = data.get(key, "")
        lines.append(f"{key}={val}\n")
        written.add(key)
    for key, val in data.items():
        if key not in written:
            lines.append(f"{key}={val}\n")
    ENV_FILE.write_text("".join(lines))


@router.get("")
async def get_settings():
    """Return current .env config; sensitive values are masked if set."""
    raw = _read_env()
    result: dict[str, str] = {}
    for key in KNOWN_KEYS:
        val = raw.get(key, "")
        result[key] = MASK if (key in SENSITIVE_KEYS and val) else val
    return {"settings": result, "env_file_exists": ENV_FILE.exists()}


class SettingsBody(BaseModel):
    settings: dict[str, str]


@router.post("")
async def save_settings(body: SettingsBody):
    """Write settings to .env. Sensitive fields only overwritten when a new non-masked value is provided."""
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
