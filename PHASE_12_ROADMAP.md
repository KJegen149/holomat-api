# Phase 12 — Authentication & Front-Door Security

**Status:** Planned. Not yet implemented.
**Goal:** Put the Holomat dashboard behind a real login. No anonymous access
to the API, the WebSocket, the MJPEG stream, or the gallery image URLs from
the moment the service starts.

---

## Why this phase exists

Today every route under `main.py` is anonymous. The only gate in the entire
app is `HOLOMAT_ADMIN_KEY` on `/api/settings/*` (`api/routes/settings.py:24`),
and even that is documented as "optional on a trusted LAN". As soon as the
kiosk's port 8100 is reachable from anything beyond the operator's couch —
guest Wi-Fi, a misconfigured tunnel, a future Cloudflare-tunnelled remote —
the Bambu printer, the camera stream, the scan library, and the `.env`
write endpoint are all reachable too.

Phase 12 closes that door with a session cookie, a JARVIS-styled login
screen, and an Argon2id-hashed password file. The kiosk experience after
the first login is unchanged for ~30 days at a time.

---

## Threat model (what this phase IS and ISN'T)

**In scope — the web surface of the API process:**
- All `/api/*` HTTP routes (camera, scan, print, gallery, generate, sources,
  ha, voice, settings, system)
- The `/api/ws` WebSocket
- The MJPEG camera stream and direct gallery image URLs (these are loaded
  by `<img src>`, so the chosen auth scheme has to work with native browser
  loaders — see "Why cookies" below)

**Out of scope — handled at the LAN layer, not the web app:**
- Wyoming TCP servers on `:10300` / `:10200` (HA dials in over raw TCP;
  the Wyoming protocol has no auth concept — these stay LAN-only)
- The SMB `HolomatSTL` share (Samba ACLs / guest config, not our problem)
- Home Assistant MQTT bridge (broker ACLs)
- The Bambu printer's own LAN MQTT (the printer is the authority there)

**Not a goal:**
- Multi-tenant accounts, RBAC, audit logs, password rotation policies.
  This is a single-user kiosk. One human, one password, one cookie.

---

## Decisions locked in (Phase 12 design)

| Decision | Choice | Rationale |
|---|---|---|
| Credential model | **Username + password** | Standard, leaves room to grow to multi-user without re-plumbing. |
| Session window | **Sliding 30-day cookie, hard cap 90 days** | Active kiosk never re-prompts; idle kiosk re-prompts after 30 days dark; no cookie outlives 90 days regardless. |
| `/api/health` | **Stays public** | Login screen can show JARVIS status pill ("OPTIMAL"/"OFFLINE") before auth — exposes only version + hardware booleans, no secrets. |
| Session model | **Stateless signed cookie** (`itsdangerous`) | One user, no logout-everywhere needed beyond "rotate the signing secret". Bumping a `session_version` counter in `auth.json` invalidates all outstanding sessions on password change. |
| Password hash | **Argon2id** (`argon2-cffi`) | Modern recommendation; bcrypt would also be fine but argon2 is the default we'd pick fresh. |
| Cookie name | `holomat_session` | |
| Cookie flags | `HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000` (+`Secure` when behind HTTPS — env-gated) | SameSite=Lax + same-origin SPA defeats CSRF without a separate token. |
| CSRF | **None beyond SameSite=Lax** | SPA and API share an origin; no cross-site form posts in play. |
| CORS | Tighten — `allow_origins` becomes the kiosk's own origin(s), `allow_credentials=True` | `["*"]` + `allow_credentials=True` is rejected by browsers anyway; today's wide-open config has to be narrowed once cookies enter the picture. |

### Why cookies, not Authorization headers / JWT-in-localStorage

Three of our surfaces are loaded by the browser without our JS in the loop:
the MJPEG stream (`<img src="/api/camera/mjpeg">`), gallery image URLs
(`<img src="/api/gallery/{id}/image">`), and the `/api/ws` WebSocket
(no easy way to send custom headers in the browser's `WebSocket` API).
A cookie is sent automatically on every same-origin request, including
those three. An `Authorization: Bearer …` header would force us to
restructure every image loader through a fetch + blob URL dance and
shim the WebSocket connect URL with `?token=…` (which then leaks into
access logs). Cookie wins on every axis that matters for a kiosk SPA.

---

## Backend implementation

### New files

**`core/auth.py`** — single source of truth for hashing, signing, and the
credential file. Public surface:

```python
def hash_password(plain: str) -> str: ...
def verify_password(plain: str, hashed: str) -> bool: ...
def issue_session(username: str) -> str: ...           # signed cookie value
def verify_session(cookie: str) -> str | None: ...     # → username, sliding refresh applied at the caller
def load_credentials() -> AuthFile: ...                # reads scan_data/auth.json
def save_credentials(username: str, plain: str) -> None: ...  # atomic write, bumps session_version
def bootstrap_if_missing() -> None: ...                # see "Bootstrap" below
```

`AuthFile` shape (in `scan_data/auth.json`, mode `0600`):

```json
{
  "username": "kjegen",
  "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$...",
  "signing_secret": "<random 32B base64url>",
  "session_version": 1,
  "created_at": "2026-05-25T18:42:00Z",
  "updated_at": "2026-05-25T18:42:00Z"
}
```

The signing secret is generated once on first run and lives only on disk
(never in `.env`, never logged). Token payload is
`{"u": username, "v": session_version, "iat": <epoch>}`; `itsdangerous`
adds the HMAC and the timestamp it uses for max-age enforcement.

The **hard 90-day cap** is enforced by checking `iat` against `now` on
every verify; the **sliding 30-day refresh** is implemented by reissuing
the cookie whenever the request comes in with a token older than ~1 day
(skip-reissue threshold avoids `Set-Cookie` on every single request).

**`api/routes/auth.py`** — the auth router:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/auth/login` | public | accepts `{username, password}`, sets cookie, returns `{username}` |
| `POST` | `/api/auth/logout` | public | clears cookie (returns 204) |
| `GET`  | `/api/auth/me` | public | returns `{username}` if cookie valid, 401 otherwise — frontend uses this on boot |
| `POST` | `/api/auth/change-password` | required | accepts `{old, new}`; bumps `session_version` so old cookies die; reissues a fresh cookie for the caller |

**`core/auth_deps.py`** (or inside `core/auth.py`) — FastAPI deps:

```python
async def require_auth(request: Request, response: Response) -> str:
    """Returns username, sliding-refreshes the cookie when appropriate.
       Raises 401 with WWW-Authenticate hint on miss."""
```

### Touching existing routers

`main.py` gets two changes:

1. `app.include_router(auth_router, prefix="/api/auth")` — new.
2. Every other `include_router(...)` call gains
   `dependencies=[Depends(require_auth)]` **except** `system_router`
   (because `/api/health` stays public — see "split the system router"
   note below).

CORS middleware (`main.py:121`) tightens:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),   # env-driven; defaults to ["http://localhost:8100"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`_allowed_origins()` reads a new env var `HOLOMAT_ALLOWED_ORIGINS`
(comma-separated). Defaults are safe for the kiosk on the box's own
hostname/IP.

### Split the system router (or carve `/api/health` out)

Today `system.py` is one router mounted at `/api`. We have two options:

- **A.** Mount `system_router` without auth, and gate the non-health
  endpoints individually with `Depends(require_auth)`.
- **B.** Move `/api/health` to a tiny standalone router with no auth,
  apply `require_auth` to the rest of `system_router`.

Pick **B** — it keeps the "this router requires auth, full stop" rule
clean for every existing router and stops `system.py` becoming the
special case.

### WebSocket auth

`api/websocket.py` already calls `await websocket.accept()`. Insert
a cookie check immediately before accept:

```python
token = websocket.cookies.get("holomat_session")
if not token or verify_session(token) is None:
    await websocket.close(code=4401)   # custom application close code
    return
await websocket.accept()
```

Document the 4401 close code on the frontend `useWebSocket` hook so it
can route the user back to the login page instead of silently reconnecting.

### MJPEG / gallery image URLs

These ride through the same `Depends(require_auth)` once their parent
routers (`camera_router`, `gallery_router`) are gated. The browser sends
the cookie automatically on `<img src>` GETs, so no client changes.

The only edge case is **HTTP Basic-style download links** — currently
none exist (gallery exposes `/api/gallery/{id}/image` and that's it).
If we ever add an "open in new tab" download, the cookie still rides
along on a top-level navigation because SameSite=Lax permits GETs.

### Brute-force throttle

Lightweight, in-process, in `core/auth.py`:

- Track `{ip: (failed_count, last_failure_ts)}` in a `dict` guarded by
  a `threading.Lock`.
- Reset on success.
- After 5 failures in a rolling 15-minute window, return `429` for that
  IP for `min(2 ** (failures - 5), 1800)` seconds (cap at 30 min).
- Independently throttle by username (same window), so a single attacker
  can't burn the kiosk's account by rotating source IPs.

Not Redis, not a real rate-limit library — this is a kiosk on one box.
If the process restarts, the throttle table is cleared; acceptable.

### Dependencies added to `requirements.txt`

```
argon2-cffi>=23.1.0     # password hashing
itsdangerous>=2.1.0     # cookie signing
```

(Both are pure-Python or have manylinux wheels for x86_64 — no apt
install needed on `KJLC-AI-01`.)

### Env vars (all optional, sensible defaults)

| Var | Default | Purpose |
|---|---|---|
| `HOLOMAT_AUTH_ENABLED` | `true` | Set `false` only for local dev; the production kiosk must run with auth on. |
| `HOLOMAT_AUTH_BOOTSTRAP_PASSWORD` | unset | If `auth.json` is missing and this is set, the first start writes it (username defaults to `holomat`). Cleared from process memory after consumption; **must be removed from `.env`** after first boot. |
| `HOLOMAT_ALLOWED_ORIGINS` | `http://localhost:8100,http://<host>:8100` | Comma-separated CORS allow-list. |
| `HOLOMAT_COOKIE_SECURE` | `false` | Set `true` when fronted by HTTPS (e.g. Cloudflare tunnel). Adds the `Secure` flag. |
| `HOLOMAT_SESSION_DAYS` | `30` | Sliding window length. Hard cap (90d) is a code constant, not env-tuneable. |

`HOLOMAT_ADMIN_KEY` is **retired**. Session auth subsumes it. The
existing `api/routes/settings.py:24` admin-gate is replaced by
`Depends(require_auth)` like every other router. Settings UI's
`X-Admin-Key` header and the localStorage `holomat_admin_key` shim
(`ui/src/api/client.ts:578`) are removed in the same PR.

---

## Frontend implementation

### New files

- `ui/src/pages/Login.tsx` — JARVIS-themed login page. Same color
  namespace (`j-*`), same radar/scan-line aesthetic as `Dashboard.tsx`.
  Username + password fields, "ENGAGE" submit button, inline error.
  Auto-focuses the username input on mount so the on-screen keyboard
  has a target immediately.
- `ui/src/hooks/useAuth.ts` — single source of truth for "am I logged
  in", "log me in", "log me out". On mount calls `GET /api/auth/me`;
  exposes `{ username, status: 'unknown'|'authed'|'anon', login, logout }`.
- `ui/src/api/auth.ts` — fetch wrappers (`login`, `logout`, `me`,
  `changePassword`).

### Wiring changes

**`ui/src/App.tsx`** — wraps `<Layout>` in an auth gate:

```tsx
const { status, username, login, logout } = useAuth()
if (status === 'unknown') return <BootSplash />     // brief "AUTHENTICATING…" frame
if (status === 'anon')    return <Login onLogin={login} />
return <Layout ...>{routes}</Layout>
```

**`ui/src/api/client.ts`** — every `fetch(...)` either gets `credentials:
'same-origin'` (which is the default, so usually nothing to change) and
a shared `_check` that treats `401` as a global auth-expired event,
bubbled to `useAuth` so the app drops back to the login screen. The
existing `AdminAuthError` plumbing is removed.

**`ui/src/components/Layout.tsx`** — adds a small `LogOut` icon button
next to the on-screen-keyboard toggle (header row), and shows the
current username in the footer near the version.

**`ui/src/pages/Settings.tsx`** — gains a "Change Password" subsection
(old + new + confirm). On success, shows a brief confirmation and stays
logged in (the change-password endpoint reissues the cookie).

### On-screen keyboard on the login screen

`OnScreenKeyboard.tsx` already works by writing into the focused element
via the native input setter and dispatching synthetic input events —
zero changes needed. Two integration details:

1. **Auto-show on Login**: `Login.tsx` calls `setShowKeyboard(true)`
   on mount; the keyboard slides up immediately so the operator can
   start typing without first tapping the keyboard toggle.
2. **Enter submits**: `OnScreenKeyboard.tsx:90-97` already handles
   `enter` by calling `el.form?.requestSubmit()`. The login form is
   a real `<form>`, so the Enter key on the on-screen keyboard works
   the same as on the password field's hardware Enter.

### Sliding-refresh on the client

Nothing to do. The cookie is HttpOnly so JS can't see it; the server
issues a fresh `Set-Cookie` on requests with stale-but-valid tokens,
and the browser swaps it in. The client only ever has to handle the
401-on-expiry case (drop to login screen).

---

## Bootstrap & operator setup

**First-run behavior** when `scan_data/auth.json` does not exist:

1. If `HOLOMAT_AUTH_BOOTSTRAP_PASSWORD` is set, create `auth.json` with
   username `holomat` and that password hash. Log a single warning:
   _"Initial credentials written. Remove HOLOMAT_AUTH_BOOTSTRAP_PASSWORD
   from .env and restart."_
2. Otherwise generate a random 16-char password, write it to disk, and
   log it **once** at WARNING level along with instructions to change
   it via Settings → Change Password.

**Forgot the password?** Operator has physical access to the kiosk
(this is a single-box install). Recovery procedure:

```
sudo systemctl stop holomat-api
rm /home/user/holomat-api/scan_data/auth.json
sudo systemctl start holomat-api   # falls back to bootstrap
journalctl -u holomat-api | grep "Initial credentials"
```

Document this in `CONFIG.md` under a new "Authentication" section.

**`auth.json` file mode:** `0600`, owned by the service user. The
existing systemd unit runs as the operator user, which matches.

---

## Non-obvious behaviour to preserve (Phase 12 traps for future Claudes)

These are the things that aren't re-derivable from reading the code
and should land in `CLAUDE.md` once Phase 12 ships:

- **`/api/health` is deliberately public** — login screen pulls it
  for the status pill. Don't "fix" this by adding `require_auth` to
  `system_router`.
- **The MJPEG stream and gallery image URLs depend on cookies, not
  on a JS fetch wrapper.** Anything that switches the kiosk's auth
  scheme to header-based tokens has to also rewrite those loaders.
  Cookies were chosen on purpose.
- **Don't widen CORS back to `["*"]`.** With `allow_credentials=True`
  the browser will refuse a wildcard origin; the wide-open default
  from pre-Phase-12 cannot coexist with the cookie.
- **`session_version` in `auth.json` is intentional** — bumping it on
  password change is what kills outstanding sessions. Don't remove it
  because "the cookie already has an expiry".
- **The 90-day hard cap is in code, not env.** Set on purpose so an
  operator can't accidentally configure a kiosk that never re-auths.
  If a future product call wants longer sessions, change the constant
  and document the threat-model rationale alongside.
- **`HOLOMAT_AUTH_BOOTSTRAP_PASSWORD` is read once at startup and
  ignored if `auth.json` already exists.** It is not a password-reset
  mechanism — see the "Forgot the password?" recovery flow.
- **WebSocket close code 4401** is our convention for "auth lapsed".
  The `useWebSocket` hook treats it as a signal to drop back to login,
  not to reconnect — leave that branch in.

---

## Out of scope (explicitly deferred)

- **TOTP / 2FA.** Single-user kiosk on a LAN with physical access; the
  marginal security doesn't justify the on-screen-keyboard UX hit.
- **Login-on-this-LAN bypass.** Considered and rejected; the user's
  intent ("cannot be accessed by outside sources and corrupted") is
  inconsistent with a LAN bypass that an attacker on the same Wi-Fi
  could also use.
- **OIDC / SSO / "Sign in with Google".** Way overkill for one human
  in front of one mat.
- **Per-route permission scopes.** All authed users are equal. If
  multi-user lands later (Phase 12.5?), revisit.
- **Audit log of logins.** Nice to have; can layer on without changing
  the cookie scheme.

---

## Acceptance criteria

1. With the service freshly installed (no `auth.json`), starting the
   process either writes a random password to the log (with clear
   "change me" warning) or consumes `HOLOMAT_AUTH_BOOTSTRAP_PASSWORD`
   from the env.
2. Hitting `http://<host>:8100/` in a fresh browser shows the JARVIS
   login screen, **not** the dashboard.
3. `curl http://<host>:8100/api/scan/library` returns 401 (was 200
   before Phase 12).
4. `curl http://<host>:8100/api/health` returns 200 (still public).
5. After login: cookie set, dashboard renders, MJPEG stream loads,
   WebSocket connects, gallery thumbnails load.
6. Browser closed and reopened within 30 days: still authed, no prompt.
7. Browser left idle 30+ days: re-prompts on next request.
8. Active session 90 days old: re-prompts regardless of recent activity.
9. Settings → Change Password: old password verified, new password
   hashed and persisted, **all other browsers** with the kiosk open
   are kicked back to login on their next request (session_version
   bump), the changing browser stays logged in.
10. Five wrong passwords in 15 minutes from the same IP returns 429
    with exponential backoff; correct password from a different IP
    still works.
11. `HOLOMAT_ADMIN_KEY` is no longer referenced anywhere; Settings
    page works without it; existing operator instructions in
    `CONFIG.md` are updated.
12. On-screen keyboard appears automatically on the login page;
    Enter on the keyboard submits the form.

---

## Implementation order (suggested PR slicing)

Two PRs, in this order, so a failed second PR can't lock the operator
out:

**PR A — backend, off by default.**
- Add `core/auth.py`, `api/routes/auth.py`, dep deps, bootstrap, throttle.
- Wire `require_auth` to every router behind a feature flag
  (`HOLOMAT_AUTH_ENABLED`, default `false` in this PR).
- Ship; verify the auth endpoints by hand with `curl`; do not gate
  the UI yet.

**PR B — frontend + flag flip.**
- Add `Login.tsx`, `useAuth.ts`, auth gate in `App.tsx`, Settings
  password-change, Logout button.
- Tighten CORS, set `HOLOMAT_AUTH_ENABLED=true` default, retire
  `HOLOMAT_ADMIN_KEY`.
- Migration note in the PR description: operators must run the
  bootstrap procedure on first restart after this PR.

---

*Phase 12 planned 2026-05-25. Implementation pending operator sign-off.*
