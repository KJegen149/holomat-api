"""Authentication endpoints — Phase 12.

Public:
  GET  /api/auth/me            — auth status (used by SPA on boot)
  POST /api/auth/login         — sets the session cookie
  POST /api/auth/logout        — clears the session cookie

Authenticated:
  POST /api/auth/change-password — verifies old, rotates session_version
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from core import auth as a
from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordBody(BaseModel):
    old: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=8, max_length=256)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/me")
async def me(request: Request) -> dict:
    """Auth status. Always public — the SPA hits this on boot."""
    if not a.auth_enabled():
        return {"username": None, "auth_enabled": False, "authenticated": True}
    token = request.cookies.get(a.COOKIE_NAME)
    if not token:
        return {"username": None, "auth_enabled": True, "authenticated": False}
    result = a.verify_session(token)
    if result is None:
        return {"username": None, "auth_enabled": True, "authenticated": False}
    payload, _ = result
    return {"username": payload["u"], "auth_enabled": True, "authenticated": True}


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response) -> dict:
    if not a.auth_enabled():
        # No-op success when the gate is off — keeps the UI testable in dev.
        return {"username": body.username, "auth_enabled": False}

    ip = _client_ip(request)
    wait = a.throttle_check(ip, body.username)
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Retry in {wait}s.",
            headers={"Retry-After": str(wait)},
        )

    creds = a.load_credentials()
    if not creds:
        log.error("Login attempted but auth.json is missing — bootstrap did not run")
        raise HTTPException(status_code=500, detail="Server credentials not initialized")

    valid = (
        body.username == creds.get("username")
        and a.verify_password(body.password, creds["password_hash"])
    )
    if not valid:
        a.throttle_record_failure(ip, body.username)
        log.warning("Failed login for %r from %s", body.username, ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    a.throttle_record_success(ip, body.username)
    a.set_session_cookie(response, a.issue_session(body.username))
    log.info("Login OK for %r from %s", body.username, ip)
    return {"username": body.username, "auth_enabled": True}


@router.post("/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    a.clear_session_cookie(response)
    return response


@router.post("/change-password")
async def change_password(
    body: ChangePasswordBody,
    response: Response,
    _username: str = Depends(a.require_auth),
) -> dict:
    if not a.auth_enabled():
        raise HTTPException(status_code=400, detail="Auth is disabled — nothing to change")
    creds = a.load_credentials()
    if not creds or not a.verify_password(body.old, creds["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password incorrect")
    a.save_credentials(creds["username"], body.new)
    # Re-issue for the caller so they don't get kicked by the session_version bump.
    a.set_session_cookie(response, a.issue_session(creds["username"]))
    log.info("Password changed for %r", creds["username"])
    return {"changed": True}
