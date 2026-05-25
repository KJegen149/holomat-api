"""Authentication — Phase 12.

Single-user kiosk auth: argon2id password hashing, signed session cookies
(itsdangerous), a tiny in-process brute-force throttle, and the credential
file at scan_data/auth.json.

See PHASE_12_ROADMAP.md for the design rationale. The most important
non-obvious bits:

  - Cookie payload carries `oiat` (original login time). Sliding reissue
    refreshes the cookie's age but preserves `oiat`, so the 90-day hard
    cap actually fires regardless of activity.
  - `session_version` lives in auth.json and is bumped on every password
    change — that is how outstanding cookies get killed.
  - `HOLOMAT_AUTH_ENABLED=false` (the default in PR-A) makes
    `require_auth` a no-op so existing routers keep working unchanged
    until PR-B flips the switch.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from core.logger import get_logger

log = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
AUTH_FILE = Path(__file__).parent.parent / "scan_data" / "auth.json"
COOKIE_NAME = "holomat_session"
DEFAULT_USERNAME = "holomat"

# Session window — sliding 30d, hard 90d cap. The hard cap is a code
# constant on purpose: an operator can't accidentally configure a kiosk
# that never re-auths.
SLIDING_DAYS = int(os.getenv("HOLOMAT_SESSION_DAYS", "30"))
HARD_CAP_DAYS = 90
RESLIDE_AFTER_SECONDS = 86400  # only re-set the cookie once per day

# Throttle — 5 failures in 15 min triggers exponential backoff (cap 30 min).
THROTTLE_WINDOW_SECONDS = 15 * 60
THROTTLE_THRESHOLD = 5
THROTTLE_MAX_DELAY = 30 * 60

_TRUTHY = ("1", "true", "yes", "on")


def auth_enabled() -> bool:
    # Default ON in production (PR-B). Set HOLOMAT_AUTH_ENABLED=false only
    # for local dev; the kiosk must never run with this off in the field.
    return os.getenv("HOLOMAT_AUTH_ENABLED", "true").strip().lower() in _TRUTHY


def cookie_secure() -> bool:
    return os.getenv("HOLOMAT_COOKIE_SECURE", "false").strip().lower() in _TRUTHY


# ── Credential file (atomic, 0600) ─────────────────────────────────────────
_FILE_LOCK = threading.Lock()
_ph = PasswordHasher()


def _now() -> int:
    return int(time.time())


def _read_file() -> Optional[dict]:
    if not AUTH_FILE.exists():
        return None
    try:
        return json.loads(AUTH_FILE.read_text())
    except Exception as e:
        log.error("auth.json unreadable (%s) — refusing to overwrite", e)
        return None


def _write_file(data: dict) -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = AUTH_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass  # non-POSIX or weird FS — still atomic-renamed below
    os.replace(tmp, AUTH_FILE)


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception as e:
        log.warning("argon2 verify error: %s", e)
        return False


def load_credentials() -> Optional[dict]:
    with _FILE_LOCK:
        return _read_file()


def save_credentials(username: str, plain: str) -> None:
    """Persist new credentials. Bumps session_version → kills all outstanding cookies."""
    with _FILE_LOCK:
        data = _read_file() or {}
        data["username"] = username
        data["password_hash"] = hash_password(plain)
        data.setdefault("signing_secret", secrets.token_urlsafe(32))
        data["session_version"] = int(data.get("session_version", 0)) + 1
        now_iso = datetime.now(timezone.utc).isoformat()
        data.setdefault("created_at", now_iso)
        data["updated_at"] = now_iso
        _write_file(data)
    log.info("Credentials updated for %r (session_version bumped)", username)


def bootstrap_if_missing() -> None:
    """First-run: write auth.json if absent. Only runs when auth is enabled
       so PR-A (auth disabled by default) doesn't create the file uninvited."""
    if not auth_enabled():
        return
    with _FILE_LOCK:
        if _read_file() is not None:
            return
        bootstrap_pw = os.getenv("HOLOMAT_AUTH_BOOTSTRAP_PASSWORD", "").strip()
        if bootstrap_pw:
            plain = bootstrap_pw
            log.warning(
                "Bootstrapping auth from HOLOMAT_AUTH_BOOTSTRAP_PASSWORD "
                "(username=%r). REMOVE that variable from .env and restart.",
                DEFAULT_USERNAME,
            )
        else:
            plain = secrets.token_urlsafe(12)
            log.warning(
                "INITIAL HOLOMAT CREDENTIALS (save these — not shown again): "
                "username=%r  password=%r  — change via Settings ASAP.",
                DEFAULT_USERNAME, plain,
            )
        now_iso = datetime.now(timezone.utc).isoformat()
        _write_file({
            "username": DEFAULT_USERNAME,
            "password_hash": hash_password(plain),
            "signing_secret": secrets.token_urlsafe(32),
            "session_version": 1,
            "created_at": now_iso,
            "updated_at": now_iso,
        })


# ── Session signing ────────────────────────────────────────────────────────
def _serializer() -> URLSafeTimedSerializer:
    creds = _read_file()
    if not creds or "signing_secret" not in creds:
        raise RuntimeError("auth.json missing or has no signing_secret")
    return URLSafeTimedSerializer(creds["signing_secret"], salt="holomat-session-v1")


def issue_session(username: str) -> str:
    """Mint a fresh cookie value. `oiat` and `iat` both start at now."""
    creds = _read_file() or {}
    now = _now()
    payload = {
        "u": username,
        "v": int(creds.get("session_version", 1)),
        "iat": now,
        "oiat": now,
    }
    return _serializer().dumps(payload)


def reissue_session(payload: dict) -> str:
    """Re-sign with a fresh `iat` but preserve `oiat` (sliding refresh)."""
    new_payload = dict(payload)
    new_payload["iat"] = _now()
    return _serializer().dumps(new_payload)


def verify_session(token: str) -> Optional[tuple[dict, bool]]:
    """Return (payload, needs_reslide) or None for invalid/expired tokens.
       needs_reslide=True when the current cookie is older than RESLIDE_AFTER_SECONDS."""
    creds = _read_file()
    if not creds:
        return None
    try:
        payload = _serializer().loads(token, max_age=SLIDING_DAYS * 86400)
    except (SignatureExpired, BadSignature):
        return None
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("u") != creds.get("username"):
        return None
    if int(payload.get("v", 0)) != int(creds.get("session_version", 1)):
        return None
    oiat = int(payload.get("oiat", 0))
    if oiat <= 0 or (_now() - oiat) > HARD_CAP_DAYS * 86400:
        return None
    iat = int(payload.get("iat", oiat))
    needs_reslide = (_now() - iat) > RESLIDE_AFTER_SECONDS
    return payload, needs_reslide


# ── Cookie helpers ─────────────────────────────────────────────────────────
def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SLIDING_DAYS * 86400,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


# ── FastAPI dependency ─────────────────────────────────────────────────────
async def require_auth(request: Request, response: Response) -> str:
    """Auth gate. No-op when HOLOMAT_AUTH_ENABLED=false (PR-A default).
       On a valid stale-ish cookie, transparently slides it forward."""
    if not auth_enabled():
        return "anonymous"
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Cookie"},
        )
    result = verify_session(token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
            headers={"WWW-Authenticate": "Cookie"},
        )
    payload, needs_reslide = result
    if needs_reslide:
        set_session_cookie(response, reissue_session(payload))
    return payload["u"]


# ── Brute-force throttle ───────────────────────────────────────────────────
# Per-IP and per-username, both checked so an attacker can't bypass by
# rotating either dimension. In-process; cleared on restart — fine for a
# single-box kiosk.
_THROTTLE_LOCK = threading.Lock()
_failures_by_ip: dict[str, list[float]] = {}
_failures_by_user: dict[str, list[float]] = {}


def _prune(history: list[float], now: float) -> list[float]:
    return [t for t in history if now - t < THROTTLE_WINDOW_SECONDS]


def _backoff_for(count: int) -> int:
    if count < THROTTLE_THRESHOLD:
        return 0
    return min(2 ** (count - THROTTLE_THRESHOLD), THROTTLE_MAX_DELAY)


def throttle_check(ip: str, username: str) -> int:
    """Seconds the caller must wait before another attempt (0 if not throttled)."""
    now = time.time()
    with _THROTTLE_LOCK:
        ip_hist = _prune(_failures_by_ip.get(ip, []), now)
        user_hist = _prune(_failures_by_user.get(username, []), now)
        _failures_by_ip[ip] = ip_hist
        _failures_by_user[username] = user_hist
        wait = max(_backoff_for(len(ip_hist)), _backoff_for(len(user_hist)))
        if wait == 0:
            return 0
        last = max(
            ip_hist[-1] if ip_hist else 0.0,
            user_hist[-1] if user_hist else 0.0,
        )
        return max(0, wait - int(now - last))


def throttle_record_failure(ip: str, username: str) -> None:
    now = time.time()
    with _THROTTLE_LOCK:
        _failures_by_ip.setdefault(ip, []).append(now)
        _failures_by_user.setdefault(username, []).append(now)


def throttle_record_success(ip: str, username: str) -> None:
    with _THROTTLE_LOCK:
        _failures_by_ip.pop(ip, None)
        _failures_by_user.pop(username, None)
