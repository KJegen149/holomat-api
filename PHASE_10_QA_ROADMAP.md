# Phase 10 — QA & Code-Revision Roadmap

**Status:** Stage 1 (audit) complete — awaiting review before any code changes.
**Scope:** Full QA pass of Phases 0–9 prior to a 1.0 release.
**Branch:** `claude/holomat-phase10-qa-4YY2l`
**Audited:** every `core/`, `api/`, `ui/src/` source file + build/deploy config (`main.py`, services, `install.sh`, scripts, `ha/*.yaml`, `config/`).

---

## How to use this document

Every finding has a stable **ID** (`C#`, `H#`, `M#`, `L#`). When a fix is applied it
will be committed referencing its ID, so this document is the index for **reverting**:

1. Find the symptom in the **Revert signal** field of each finding.
2. The ID maps 1:1 to a commit (Stage 2 commits one logical batch each, message prefixed with the IDs).
3. `git revert <commit>` restores the prior behaviour; this doc tells you what that behaviour was.

**Severity model**
| Level | Meaning |
|---|---|
| **Critical** | Live credential committed, or unauthenticated remote write/code-exec. Blocks 1.0. |
| **High** | Breaks a feature, violates a hard CLAUDE.md rule, or leaks private infrastructure. |
| **Medium** | Maintainability: spaghetti, duplication, dead code, remnants with minor impact. |
| **Low** | Cosmetic: stale comments, naming, minor inconsistency. |

> **Secret hygiene for this file:** credential *values* (access codes, keys, passwords)
> are referenced by location only, never reproduced here, so the roadmap itself stays clean.

---

## Summary counts

| Severity | Count | IDs |
|---|---|---|
| Critical | 5  | C1–C5 |
| High     | 16 | H1–H16 |
| Medium   | 25 | M1–M25 |
| Low      | 29 | L1–L29 |
| **Total**| **75** | |

---

## Decisions needed before Stage 2

These findings have more than one defensible fix. Stage 2 will not start the affected
items until you choose.

| # | Decision | Affects | Recommendation |
|---|---|---|---|
| **D1** | Cloud printer path: **delete** it for a LAN-only 1.0, or **keep** it behind an explicit `BAMBU_USE_CLOUD` flag? | C3, H4, M-cloud | Delete — printer is LAN-only; the path is broken and unreachable-by-intent. |
| **D2** | `core/printer_lan.py` (dead 300-line rollback copy): **delete** (rely on a git tag) or **move** to `archive/`? | H4 | Delete; tag the pre-cloud commit instead. |
| **D3** | Dev test scripts (`test_bambu.py`, `scripts/test_*.py`): **move** to `tools/` or **delete**? | C2, M16, M17 | Move to `tools/` (excluded from release), strip the hard-coded creds from `test_bambu.py`. |
| **D4** | Settings API auth: **token/API-key header** on the router, or **bind backend to `127.0.0.1`** + reverse-proxy? | C4 | Token header — the UI is served from the same host and a kiosk can hold a key. |
| **D5** | `addManualObject` (backend route exists, no UI): **build the manual-add UI** or **remove the dead client fn**? | M21 | Your call — is manual object entry a 1.0 feature? |
| **D6** | `ha/jarvis_dashboard.yaml` (personal HA config, contains household PII): **keep**, **sanitise**, or **remove from repo**? | L26 | Remove from the app repo — it is not application code. |
| **D7** | Git history: the Bambu access code & RSA key are in past commits. **Rotate** the code (always) and optionally **scrub history**. | C1, C2, C3 | Rotate the printer access code regardless. Scrub only if the repo is/will be public. |

---

# CRITICAL

### C1 — Live Bambu LAN access code committed in `.env.example`
- **File:** `.env.example:6,16,17,21,28`
- **What:** `.env.example` ships **real values**, not placeholders: a live 8-digit `BAMBU_ACCESS_CODE`, the printer `BAMBU_SERIAL`, `BAMBU_IP`, the private `HA_URL` hostname, and the `CF_API_URL` worker endpoint.
- **Why it must change:** The access code is the LAN credential that controls the 3D printer; it is git-tracked and pushed. An example file must contain placeholders only.
- **Impact if left:** Anyone with repo access can dispatch prints / read printer state on the LAN. Secret scanners may flag the release.
- **Fix:** Replace every value with a placeholder (`BAMBU_ACCESS_CODE=`, `BAMBU_IP=192.168.x.x`, `BAMBU_SERIAL=your_printer_serial`, `HA_URL=https://ha.example.com`). **Rotate the printer access code** (Settings → Network on the printer).
- **Revert signal:** None — `.env.example` is documentation, never read at runtime. App boots from `.env`. Zero functional risk.

### C2 — Live Bambu credentials hard-coded in root `test_bambu.py`
- **File:** `test_bambu.py:13-15`
- **What:** `PRINTER_IP`, `ACCESS_CODE`, `SERIAL` are hard-coded string literals at module top. The file is a dev smoke-test sitting at repo root (also caught by `pytest` discovery).
- **Why it must change:** Same live LAN credential as C1, plus a loose `test_*.py` in the repo root is a remnant.
- **Impact if left:** Credential exposure; running it triggers a real printer connection.
- **Fix:** Move to `tools/` (D3), make it read `os.getenv` like `scripts/test_bambu_print.py` already does. Or delete — `scripts/test_bambu_print.py` supersedes it.
- **Revert signal:** None — standalone script, imported by nothing. Removing/moving it cannot affect the running app.

### C3 — RSA private key embedded in `core/bambu_signing.py`
- **File:** `core/bambu_signing.py:26-54` (key block), `:61` (unconditional import-time load)
- **What:** A full `-----BEGIN PRIVATE KEY-----` PEM block is a source-code constant; line 61 calls `serialization.load_pem_private_key(...)` at import, with no guard.
- **Why it must change:** A committed private-key block trips every secret scanner (GitHub push-protection, gitleaks) and blocks a 1.0 tag. Per the file's own docstring it is the *community-extracted, expired (Dec 2025)* Bambu Connect key — not Holomat's secret — but a scanner cannot tell. Import-time load means any future top-level import crashes the app if the key is ever malformed.
- **Impact if left:** Release tagging blocked; legally grey to ship; latent startup-crash risk.
- **Fix:** Tied to **D1**. If cloud path is dropped: delete `bambu_signing.py` entirely. If kept: remove the literal, load **only** from `BAMBU_APP_PRIVATE_KEY` env var, and make `_rsa_key` lazy (loaded inside `sign_mqtt_payload`, cached) with a clear error if unset.
- **Revert signal:** Only the cloud print path uses this (`core/printer.py:249`, lazy import). With the printer LAN-only the path is unreachable-by-intent → deletion has **zero runtime impact**. Detect any regression by running the LAN print test (`scripts/test_bambu_print.py`) — a cube must still print.

### C4 — `api/routes/settings.py` has zero authentication on every endpoint
- **File:** `api/routes/settings.py` — all routes; router mounted at `main.py:145`
- **What:** `GET /api/settings`, `POST /api/settings`, `POST /api/settings/restart`, `GET /api/settings/test*`, `POST /api/settings/bambu-auth` are all anonymous. The backend binds `0.0.0.0`.
- **Why it must change:** Any LAN client can rewrite the `.env` credential file, force-kill the process (`/restart` → `os._exit(1)`), and trigger credentialed outbound auth attempts. This is the most security-sensitive route in the project and it is wide open.
- **Impact if left:** Full credential compromise + remote DoS from anywhere on the LAN.
- **Fix:** Tied to **D4**. Add an auth dependency to the whole router (`APIRouter(dependencies=[Depends(require_api_key)])`) checking a header against a stored key; or bind the server to `127.0.0.1` behind a proxy. At minimum gate `POST /settings` and `/restart`.
- **Revert signal:** After the fix, the Settings page must send the key. If the Settings tab returns 401 / fails to load or save, the UI client (`ui/src/api/client.ts` settings calls) was not updated to send the credential.

### C5 — `_write_env` performs no escaping → `.env` injection & corruption
- **File:** `api/routes/settings.py:75-87` (`_write_env`), `:65-72` (`_read_env`)
- **What:** `_write_env` writes `f"{key}={val}\n"` raw — no quoting, no escaping, no key validation. `_read_env` asymmetrically `strip("\"'")`s on read. The POST body model is `dict[str,str]`; JSON string values may contain `\n`.
- **Why it must change:** (a) **Injection** — a posted value containing a newline injects an extra `.env` line (e.g. a second `HA_TOKEN=`), a credential-injection vector (reachable anonymously via C4). (b) **Corruption** — a password containing `#`, `$`, quotes, or leading/trailing spaces round-trips wrong. (c) The write is non-atomic (see H14).
- **Impact if left:** Credential injection and silent credential corruption.
- **Fix:** Validate keys against `^[A-Z0-9_]+$`; reject values containing `\n`/`\r`; quote-and-escape every value on write. Add a Pydantic field validator.
- **Revert signal:** Old unquoted `.env` files must still parse — `_read_env`'s existing `strip` tolerates both forms, so low risk. If a saved password with special characters reads back wrong, the escape/quote logic is faulty.

---

# HIGH

### H1 — `install.sh` references forbidden `OPENAI_API_KEY` and a stale version
- **File:** `install.sh:18` (`v0.2.0`), `:107-110` (`OPENAI_API_KEY`)
- **What:** The installer's closing instructions tell the user to set `Environment=OPENAI_API_KEY=...`; the banner says `v0.2.0`.
- **Why:** CLAUDE.md: *"Do NOT introduce `openai`, `gpt-*`, or `OPENAI_API_KEY` anywhere."* The app never reads `OPENAI_API_KEY` — following this instruction sets a dead variable and misleads the operator. Version is 4 releases stale.
- **Impact if left:** Operator confusion; project-rule violation; forbidden string in repo.
- **Fix:** Replace the `OPENAI_API_KEY` lines with `GEMINI_API_KEY`; bump the banner to the release version.
- **Revert signal:** Cosmetic / docs only — no runtime effect.

### H2 — `holomat-api.service` commits real infrastructure identifiers
- **File:** `holomat-api.service:19-25`
- **What:** `Environment=` lines embed the real `BAMBU_SERIAL`, `BAMBU_IP`, `HA_URL`, `HA_MQTT_USER`, `CF_API_URL`.
- **Why:** A git-tracked unit file should not carry host-specific values. No passwords/codes here (those are correctly documented as `systemctl edit` drop-ins), but serial + internal IP + private hostname are recon-grade infrastructure data.
- **Impact if left:** Infrastructure disclosure; the file is not portable to any other host.
- **Fix:** Move host-specific values to a `systemctl edit` drop-in (the file already documents this pattern for secrets), or commit a `holomat-api.service.example` and gitignore the real one.
- **Revert signal:** If the env vars are removed without a replacement source, the service loses `BAMBU_IP`/`HA_URL` at boot → `GET /api/health` shows empty `services.ha_url`, printer dispatch fails. Keep the drop-in in place.

### H3 — Forbidden OpenAI/GPT references in source
- **Files:** `core/scanner.py:170` (`# Encode full undistorted frame for GPT-4o`), `core/voice_bridge.py:163` (`Attribution(name="OpenAI / Groq", ...)`)
- **What:** A stale comment naming GPT-4o (the code below it calls Gemini), and a Wyoming STT attribution string naming OpenAI.
- **Why:** CLAUDE.md forbids `openai`/`gpt-` strings. The scanner comment is factually wrong (project uses Gemini Vision). The voice attribution reflects a real fact — STT genuinely runs Whisper via the Cloudflare worker — which is an **unstated exception** to "Gemini only".
- **Impact if left:** Rule violation; misleading comments.
- **Fix:** `scanner.py:170` → `# Encode full undistorted frame for Gemini Vision`. `voice_bridge.py:163` → `name="Cloudflare Workers AI"`. **Also update CLAUDE.md** to record that STT/TTS use Whisper/Deepgram via Cloudflare — an intentional carve-out from the Gemini-only rule.
- **Revert signal:** None — comment/display strings only.

### H4 — `send_and_print()` mis-routes to the broken cloud path
- **File:** `core/printer.py:48-49` (`is_cloud_configured`), `:495-510` (`send_and_print`); cloud branch `:130-275`; `requirements.txt:13-14`
- **What:** `send_and_print()` does `if is_cloud_configured(): _cloud_send_and_print(...)`. `is_cloud_configured()` is true when `BAMBU_EMAIL + BAMBU_PASSWORD + BAMBU_SERIAL` are set — but the **LAN path also needs** `BAMBU_EMAIL`/`PASSWORD` (for `_get_user_id()`). So the documented 5-variable setup **always routes to cloud**. The cloud path does `from bambulab import ...` — a package **not in `requirements.txt`** (which lists `bambulabs-api` and an unused `bambu-lab-cloud-api`). The `send_and_print` docstring also says cloud is "preferred" and LAN "requires touchscreen confirmation" — both contradict CLAUDE.md (LAN is active and auto-starts via `user_id`).
- **Why:** This is the most likely root cause of CLAUDE.md's unresolved *"Phase 7 final test did not print"*: the test routes into an `ImportError` path.
- **Impact if left:** Printing is broken for any correctly-configured system.
- **Fix:** Tied to **D1**. Recommended (LAN-only 1.0): delete the cloud branch (`_cloud_send_and_print`, `_get_bambu_client`, `is_cloud_configured`, the `if` at `:503`), so `send_and_print` always uses `_lan_send_and_print`; drop `bambu-lab-cloud-api` from requirements; rewrite the docstring. If keeping cloud: gate it behind an explicit `BAMBU_USE_CLOUD=true` flag and add the correct package.
- **Revert signal:** After the fix a queued print must auto-start via LAN (log line `Using LAN mode...`, printer shows `AUTO-STARTED`). If prints stop dispatching, re-check `_lan_send_and_print` / `_get_user_id`.

### H5 — Version & phase strings drift across the whole project
- **Files:** `main.py:2,54,121`; `api/routes/system.py:22-23` (`0.6.0` / `Phase 6`); `core/ha_bridge.py:35` (`sw_version 0.3.0`), `:234` (hard-coded `Phase 4`); `install.sh:18` (`0.2.0`); `ui/package.json:3` (`0.2.0`); `ui/src/components/Layout.tsx:121` (`v0.9.0 // PHASE 9`).
- **What:** Seven sources report the version/phase; they disagree (`0.2.0` / `0.3.0` / `0.6.0` / `0.9.0`). `GET /api/health` and the HA "Current Phase" sensor both report wrong data.
- **Why:** Directly blocks the requested **1.0 bump** — there is no single source of truth.
- **Impact if left:** Health endpoint, HA sensors, UI footer, and OpenAPI docs all show wrong/conflicting versions.
- **Fix:** Create one constant (e.g. `core/version.py: VERSION = "1.0.0"`), import it in `main.py`, `system.py`, `ha_bridge.py`; drive the UI footer from `health.version`/`health.phase`; set `package.json` to `1.0.0`; bump `install.sh`.
- **Revert signal:** Cosmetic — verify no test asserts a literal old version string. `GET /api/health` should report `1.0.0`.

### H6 — `library.json` has no write lock; a parse error wipes the library
- **File:** `core/scanner.py:46-81` (`_load_library`/`_save_library`), `:311-356` (`update_object`/`delete_object`/`_add_to_library`)
- **What:** Read-modify-write of `scan_data/library.json` with **no lock** (a known CLAUDE.md open issue — confirmed never fixed; no `threading` import in the file). Separately, `_load_library` catches all exceptions and returns `[]`; the next `_save_library` then **overwrites the corrupt-but-recoverable file with an empty list**.
- **Why:** `scan_object` `await`s a Gemini call mid-sequence — a PATCH/DELETE can interleave between load and save (lost update). A transient read error silently destroys up to 50 saved objects.
- **Impact if left:** Object library data loss.
- **Fix:** Add a module-level `threading.Lock` around load+mutate+save (the camera singleton already uses this pattern). On `_load_library` parse failure, back up the bad file (`library.json.corrupt`) and refuse to auto-overwrite.
- **Revert signal:** Load-test concurrent `/api/scan/capture` + library PATCH; the lock must never be held across an `await`. If scans hang, the lock is mis-scoped.

### H7 — `height_mm or 20.0` treats a valid `0.0` as unset
- **File:** `api/routes/scan.py:142`
- **What:** `height_mm = entry.get("height_mm") or 20.0` — a stored height of exactly `0.0` (a value the API explicitly allows: `Field(None, ge=0)`) becomes `20.0`. Known CLAUDE.md open issue — confirmed still present.
- **Why:** A flat object gets a 20 mm-tall case cavity.
- **Impact if left:** Wrong generated-case geometry for zero-height objects.
- **Fix:** `height_mm = entry.get("height_mm"); if height_mm is None: height_mm = 20.0`.
- **Revert signal:** Generate a case for a `0.0`-height object — cavity height should be `0`, not `20`. (Low real-world incidence: scans store `null`, not `0.0`.)

### H8 — Undefined Tailwind colour tokens break all error styling
- **Files:** `ui/tailwind.config.ts:8-19`; used in `OnScreenKeyboard.tsx`, `Voice.tsx`, `Settings.tsx` (`j-err` ×20), `Gallery.tsx` (`j-surface` ×4)
- **What:** The `j` palette defines `red` and `surf` but **not** `err` or `surface`. Verified: `j-err` (20 uses) and `j-surface` (4 uses) generate no CSS.
- **Why:** Every error banner in Settings/Voice and the on-screen-keyboard close button render colourless; every Gallery card/panel renders without its surface background.
- **Impact if left:** Error states are invisible; Gallery looks broken.
- **Fix (lowest-risk):** Add aliases to the palette — `err: 'rgb(232 48 64 / <alpha-value>)'`, `surface: 'rgb(10 13 18 / <alpha-value>)'`. (Purely additive; no existing class changes.) Alternatively rename all usages to `j-red`/`j-surf`.
- **Revert signal:** Trigger a Settings test failure — error text must be red; Gallery cards must have a dark panel background.

### H9 — `HomeAssistant.tsx` hard-codes the private HA hostname in shipped UI
- **File:** `ui/src/pages/HomeAssistant.tsx:35`
- **What:** The "not configured" help text hard-codes a real private HA hostname. Every other page uses the neutral `https://ha.example.com`.
- **Why:** Leaks a real internal hostname into shipped UI source and the rendered DOM.
- **Impact if left:** Infrastructure disclosure.
- **Fix:** Change to `https://ha.example.com` (matches `Settings.tsx:55`).
- **Revert signal:** None — display-only placeholder inside the `if (!haUrl)` empty state. The real iframe URL comes from `health.services.ha_url`.

### H10 — Five `asyncio.get_event_loop()` calls violate the async rule
- **Files:** `core/logger.py:23`; `api/routes/calibration.py:52,99`; `core/camera.py:64`; `api/routes/camera.py:30`
- **What:** Deprecated `get_event_loop()` where CLAUDE.md mandates `get_running_loop()`. The `logger.py` one is worst: log records emitted from daemon threads (HA bridge, print queue, voice loop) hit it with no running loop → `RuntimeError` → swallowed → **cross-thread log lines silently dropped from the UI console**.
- **Why:** Explicit CLAUDE.md rule violation; one instance has real impact (lost logs); all emit `DeprecationWarning`.
- **Impact if left:** Missing log lines in the JARVIS console; future Python may make the others hard errors.
- **Fix:** `logger.py` — capture the running loop once in `setup_logging()`, store it, use `loop.call_soon_threadsafe`. The other four — swap to `asyncio.get_running_loop()` (zero behaviour change inside a coroutine).
- **Revert signal:** Camera stream + calibration capture must still work. After the logger fix, worker-thread logs (HA push, print job) should now appear in the UI console.

### H11 — Print-queue persistence is non-atomic; a mid-write crash loses the queue
- **File:** `core/print_queue.py:50-72` (`_save_jobs`/`_save_profiles`), `:101,108` (unlocked profile mutation)
- **What:** `QUEUE_FILE.write_text(...)` overwrites the live file directly. A crash mid-write truncates `print_queue.json`; `_load()` then catches the `JSONDecodeError` and silently resets `self._jobs = []`. Profile create/delete call `_save_profiles` outside the asyncio lock.
- **Why:** Total, silent queue loss on power-loss/restart during a write; lost-update race on profiles.
- **Impact if left:** Print queue and custom slicer profiles can vanish without warning.
- **Fix:** Write to a temp file in the same dir, then `os.replace()` (atomic). Guard profile mutation with the same lock.
- **Revert signal:** Queue a job, restart the server — the job must survive (`GET /api/print/queue`). If jobs vanish, the temp-write/rename is faulty.

### H12 — A stalled print is marked `done` at 100%
- **File:** `core/print_queue.py:169-242` (`_process_job`)
- **What:** The status poll is `for _ in range(2880): await asyncio.sleep(10)` (~8 h). If it exhausts without ever observing a terminal printer state (`IDLE/FINISH/FAILED/STOP`), the code falls through to `state="done"`, `progress=100`.
- **Why:** A print that stalls (printer stops reporting) is recorded as a success.
- **Impact if left:** Queue shows a failed/stuck job as completed.
- **Fix:** Track whether a terminal state was actually observed; if the loop exhausts without one, set `state="failed"`, `error="timeout waiting for printer"`.
- **Revert signal:** A normal print must still end `done` with a real terminal state in the logs. If genuine completions get marked failed, the terminal-state check is too strict.

### H13 — `settings.py` imports the wrong Bambu package
- **File:** `api/routes/settings.py:329,398`
- **What:** `from bambulab import BambuAuthenticator, BambuClient`. The rest of the project uses `bambulabs_api` (the `bambulabs-api` package). `import bambulab` is an `ImportError` at runtime, masked by `# type: ignore`.
- **Why:** `GET /api/settings/test/bambu` (cloud-auth probe) and `POST /api/settings/bambu-auth` always fall into `except → {"ok": False, "detail": "No module named 'bambulab'"}`. A plausible contributor to the Phase 7 auth troubles. (`core/printer.py:134` shares the same bug — fold into H4.)
- **Impact if left:** Bambu cloud-auth / OTP features in Settings are permanently broken.
- **Fix:** Change to `from bambulabs_api import ...`; verify the actual class names match that package's API surface.
- **Revert signal:** Hit `/api/settings/test/bambu` — it must return a real auth result, not "No module named". If it errors differently, the class names differ.

### H14 — `.env` write in `settings.py` is non-atomic and unlocked
- **File:** `api/routes/settings.py:75-87`, `:107-130` (`save_settings`)
- **What:** `save_settings` does `_read_env()` → mutate → `_write_env()` with no lock and a non-atomic `write_text`. Concurrent POSTs race (lost update); a crash mid-write truncates the file.
- **Why:** The `.env` file holds *every* project credential — higher blast radius than the `library.json` race CLAUDE.md already flags.
- **Impact if left:** Loss of all stored credentials on an unlucky write.
- **Fix:** Temp-file + `os.replace()`; guard read-modify-write with a `threading.Lock`. (Pairs naturally with the C5 escaping fix.)
- **Revert signal:** Hammer `POST /api/settings` concurrently — `.env` must stay valid and contain all keys.

### H15 — Hand-rolled `.env` parser diverges from `python-dotenv`
- **File:** `api/routes/settings.py:65-72` (`_read_env`)
- **What:** `_read_env` splits on `=` and strips quotes. It does **not** handle a leading `export ` (parses key as `"export HA_TOKEN"`) or inline `# comments` (value becomes `10300  # default`). The app actually loads `.env` via `python-dotenv` (`main.py:22`), which *does* handle both.
- **Why:** The Settings UI shows different values than the process really has; a save round-trip corrupts `export`-prefixed lines.
- **Impact if left:** Settings UI displays/writes wrong values for hand-edited `.env` files.
- **Fix:** Use `dotenv.dotenv_values(ENV_FILE)` (python-dotenv is already a dependency) for reads.
- **Revert signal:** Parse an `export`-prefixed `.env` and a value with an inline comment — both must read back correctly.

### H16 — Gallery injects unsanitised remote SVG via `dangerouslySetInnerHTML`
- **File:** `ui/src/pages/Gallery.tsx:61` (`SvgModal`)
- **What:** `<div dangerouslySetInnerHTML={{ __html: svg }} />` renders SVG returned by `galleryGenerateSvg` (a Cloudflare worker / AI output). SVG can carry `<script>` and event-handler attributes.
- **Why:** An XSS sink. The source is first-party today, but unsanitised HTML injection of remote content is a known stored-XSS vector — and the kiosk UI has no other content-security boundary.
- **Impact if left:** Script execution in the UI if the worker is ever compromised or the model emits a script tag.
- **Fix:** Sanitise with DOMPurify (`USE_PROFILES: { svg: true, svgFilters: true }`) before injection, or render the SVG as an `<img>` data-URI / sandboxed iframe.
- **Revert signal:** Generate an SVG and confirm it still renders identically in the modal. If filters/animations vanish, the sanitiser profile is too strict.

---

# MEDIUM

> Maintainability debt. None of these break a feature or expose a secret. Compact entries — file, issue, fix, revert note.

### M1 — Duplicated calibration-status payload
`api/routes/calibration.py:35-46` vs `api/routes/system.py:38-43` build the same `{valid,captured_at,point_count,rmse}` dict. **Fix:** add `cal.status_summary()` in `core/calibration.py`, call from both. **Revert:** the JSON shape of `/api/calibration/status` and `/api/health` must stay byte-identical.

### M2 — Calibration session global has no lock
`api/routes/calibration.py:23-31` — module-global `_session` mutated by capture/compute/reset with no synchronisation; executor threads append to a shared list. **Fix:** guard with a `threading.Lock`, or document the single-client assumption. **Revert:** run the full capture→compute sequence; count must increment correctly.

### M3 — `ha_bridge` reaches into `api/` and re-imports every 30 s
`core/ha_bridge.py:219-225` — `_push_state` does function-scoped imports of `core.*` **and `api.websocket`** (a `core → api` layering inversion) on every 30 s tick; `_ENTITIES` (`:38-88`) and the `state_map` (`:236-239`) are parallel structures kept in sync by hand with a silent `"unknown"` fallback. **Fix:** hoist imports if no real cycle; attach a value-provider to each `_ENTITIES` entry. **Revert:** promoting imports may surface a real circular import → app fails to boot; keep inline if so.

### M4 — `mjpeg_stream` has no per-frame error handling
`core/camera.py:62-83` — if `cv2.imencode` fails, `buf.tobytes()` raises and tears down the whole stream. **Fix:** check the `imencode` success flag, `continue` on failure. **Revert:** stream for a long period; feed must survive occasional bad frames.

### M5 — Duplicated compile-route tail in `generate.py`
`api/routes/generate.py:227-244` and `:258-287` share an identical mkdir→filename→compile→respond block. **Fix:** extract `async def _compile_and_respond(code, name)`. **Revert:** `/api/generate/openscad` and `/compile-case` must return identical response shapes.

### M6 — Markdown-fence stripping duplicated
`core/scanner.py:247-251` and `api/routes/generate.py:90-94` — byte-identical fence-strip blocks. **Fix:** shared `core/gemini_util.strip_code_fences()`. **Revert:** exercise scan-identify and case-gen with fenced Gemini output.

### M7 — `identify_image` has an unused `mime` parameter
`core/scanner.py:220` — `mime` is never used (PIL sniffs the format). **Fix:** delete the parameter (only one in-repo caller, passes nothing). **Revert:** `grep identify_image` — confirm no external keyword call.

### M8 — `_generate_case_openscad` now has 3 cross-module call sites
`api/routes/generate.py:41` — used twice in `generate.py` and imported lazily into `scan.py:144`. CLAUDE.md's rule says move it to `core/` once a third caller exists. **Fix:** move `_generate_case_openscad` + `_builtin_case_template` to `core/case_gen.py`; import from there in both. **Revert:** exercise `/generate/case`, `/generate/compile-case`, `/scan/generate-case`.

### M9 — Cloud printer path is dead weight
`core/printer.py:130-275` + `core/bambu_signing.py` exist only for the unreachable cloud path (see H4/C3). **Fix:** delete with H4 (decision **D1**). **Revert:** LAN print must still dispatch.

### M10 — `core/printer_lan.py` is a dead 300-line file
Confirmed **0 imports** repo-wide. It is a stale verbatim fork of `printer.py`'s LAN logic and still contains the known-broken `ftp:///cache/` URL CLAUDE.md warns about — not a safe rollback target. **Fix:** delete (decision **D2**); tag the pre-cloud commit for rollback. **Revert:** none — nothing imports it.

### M11 — `_process_job` is a 74-line mixed-responsibility function
`core/print_queue.py:169-242` — slicing + upload + MQTT + an 8 h poll in one function. **Fix:** extract slice/upload/poll helpers (pairs with H12). **Revert:** a normal print must still progress queued→slicing→…→done.

### M12 — `print_queue._worker` reads `self._jobs` unlocked
`core/print_queue.py:248` — list comprehension over shared state with no `async with self._lock`. Safe in today's cooperative scheduling but inconsistent with the rest of the class. **Fix:** snapshot under the lock. **Revert:** none — defensive.

### M13 — `__import__('os')` hack inside `print_queue`
`core/print_queue.py:181,184-191` — two different inline-import idioms for `os` in one function. **Fix:** add `import os` at module top, use it throughout. **Revert:** none — identical behaviour.

### M14 — SMB watcher can double-process a file
`core/smb_watcher.py:107-157` — `on_created` and `on_closed` both fire; the `_seen` guard is `discard`ed in `_process`'s `finally`, leaving a re-process window. **Fix:** keep processed paths in `_seen` with a short TTL, or `path.exists()`-check before reprocessing. **Revert:** drop one file → exactly one `Gallery ingest OK` log line.

### M15 — Gallery routes don't catch upstream HTTP errors
`api/routes/gallery.py:53-115` etc. — `r.raise_for_status()` is uncaught except for 404; `list_gallery` has no try/except. An upstream CF 500/timeout yields a bare stack-trace 500, inconsistent with the deliberate `_no_cf()` 503 pattern. **Fix:** wrap `httpx` calls in `try/except httpx.HTTPError` → structured 502/503. **Revert:** hit a gallery route with CF unreachable → expect JSON error, not a trace.

### M16 — Dev scripts are footguns in the product repo
`scripts/test_bambu_print.py`, `scripts/test_orca_project3mf.py`, root `test_bambu.py` — runnable real-printer dispatch tools; `test_bambu_print.py` echoes the printer serial to stdout; `test_*` names get pytest-collected. (Note: `scripts/test_*` read `.env` correctly — **no** hard-coded secrets there; only root `test_bambu.py` has them, see C2.) **Fix:** move all three to `tools/` (decision **D3**), mask the serial in stdout. **Revert:** update the CLAUDE.md path reference; the documented `python3 scripts/...` workflow changes.

### M17 — SMB share path is hard-coded and fragile
`config/samba.conf:11`, `scripts/setup_samba.sh:7-8,26` hard-code `/home/jarvis/holomat-api/smb_share` and user `jarvis`; `core/smb_watcher.py:29` watches the repo-relative `smb_share/`. They align **only** if the repo is deployed at exactly `/home/jarvis/holomat-api`. On any other path the ingest pipeline silently breaks; `setup_samba.sh` fails outright if there is no `jarvis` user. **Fix:** derive the path from `$PWD`/`$(whoami)` in the setup script and config; align all three on one value. **Revert:** drop an image on the share → confirm a `Gallery ingest OK` log line and the file disappearing.

### M18 — Duplicated test-STL builders
`scripts/test_bambu_print.py:34-62` and `scripts/test_orca_project3mf.py:22-50` — copy-pasted cube-face data and binary-STL writers. **Fix:** shared `tools/_test_geometry.py` (with M16's move). **Revert:** none — dev scripts only.

### M19 — `voice_bridge` STT/TTS handlers are ~100 lines of copy-paste
`core/voice_bridge.py:137-276` (session handlers) and `:371-397` (server coroutines) are near-duplicates differing only by port/handler. **Fix:** factor `_run_server(handler, port, label)` and a shared session wrapper — cuts ~80 lines. **Revert:** add the Wyoming integration in HA; STT + TTS must both still work.

### M20 — `voice_bridge` dead `rolling` buffer
`core/voice_bridge.py:444,448,451-453,469` — a "3-second wake-word context" buffer is filled, trimmed, and cleared but **never read**. Confirmed: zero reads. The comment advertises a feature that does not exist. **Fix:** delete the buffer and its maintenance. **Revert:** none — unreachable as data.

### M21 — Dead client API surface
`ui/src/api/client.ts:172-174` (`fetchScanObject`) and `:176-182` (`addManualObject` + `ManualObjectBody` interface) — confirmed **0 references** outside `client.ts`. `addManualObject` has a live backend route but no UI. **Fix:** remove the dead exports — **or**, for `addManualObject`, build the manual-add UI (decision **D5**). **Revert:** `tsc -b` fails loudly on a wrongful removal.

### M22 — Five duplicated response-checker helpers
`ui/src/api/client.ts` — `_checkScan/_checkGallery/_checkPrint/_checkVoice/_checkSettings` (`:148,239,330,413,444`); four are byte-identical, `_checkScan` is subtly different (untyped, missing the `error` fallback). **Fix:** collapse to one generic `_check<T>`. **Revert:** smoke-test a scan + case-generate; `tsc -b` must pass.

### M23 — Repeated polling/error pattern across hooks
`ui/src/hooks/{useHealth,useCalibration,usePrint,useScanner}` each re-implement fetch-on-mount + `setInterval` + cleanup, and copy the `instanceof Error` mapping ~15×. **Fix:** extract `usePolling(fn, ms)` + `errMsg(e, fallback)`. **Revert:** each page must still live-update (health pill, capture count, print queue, background status).

### M24 — `health` is prop-drilled and double-fetched
`ui/src/App.tsx:16,21,23` drills `health` into `Layout`/`Dashboard`/`HomeAssistant`; `Settings.tsx` *also* calls `fetchHealth` directly → redundant polling. **Fix:** a `HealthContext` provider; remove the separate `fetchHealth`. **Revert:** confirm exactly one `/api/health` poll in the network tab and all pages still reflect live health.

### M25 — Settings: GET shows stale config; `/restart` is ungraceful; missing keys
`api/routes/settings.py` — (a) `_resolve` falls back to `os.getenv` (frozen at process start) so GET can show a value the process no longer uses (`:90-105`); (b) `/restart` (`:131-139`) does `os._exit(1)`, skipping cleanup — can truncate an in-flight `print_queue.json`/`library.json` write, and relies on an undocumented `Restart=` policy; (c) `KNOWN_KEYS` omits `BAMBU_TOKEN_FILE`/`BAMBU_FTP_PORT`/`BAMBU_MQTT_PORT` that the test endpoints use. **Fix:** label process-env-derived values; use a graceful restart (exit 0 + `Restart=always`, or `systemctl`); reconcile `KNOWN_KEYS`. **Revert:** the Settings "restart" button must still bring the service back; the Settings form must still populate.

---

# LOW

> Cosmetic / stale. Safe, near-zero-risk cleanups. Batch these into a single commit.

| ID | File:line | Issue | Fix |
|---|---|---|---|
| L1 | `core/camera.py:2-3` | Docstring frozen at "Phase 1/4" | Trim to a timeless description |
| L2 | `core/calibration.py:13` | Docstring overstates "blocks boot" — nothing enforces it | Reword to "clients should gate the UI" |
| L3 | `core/calibration.py:4` | Persistence under `calibration_data/` undocumented vs `scan_data/` | Note it in CLAUDE.md |
| L4 | `core/calibration.py:101` | `_m_ids` underscore-prefixed but used | Rename to `marker_ids` |
| L5 | `core/slicer.py:14-16,332-334` | Module docstring says `--load-settings` NOT used; code uses it | Rewrite docstring to match code |
| L6 | `core/slicer.py:78-84` | `openscad --version` spawned twice | Capture `stderr+stdout` in one call |
| L7 | `core/slicer.py:49-53` | Dead `QUALITY_PROFILES` dict — 0 refs (verified) | Delete |
| L8 | `api/routes/generate.py:112` | `// Generated by Holomat Phase 4F` baked into SCAD | Drop the phase number |
| L9 | `core/scanner.py:225-231,264-270` | "Unknown Object" dict duplicated | Extract `_UNKNOWN_IDENTITY` constant |
| L10 | `api/routes/scan.py:149-155` | `entry["width_mm"]` bracket access → `KeyError`; dead `try/except` around a non-raising call | Use `.get(...)` |
| L11 | `api/routes/system.py:2` | Dead `import shutil` — 0 refs (verified) | Delete |
| L12 | `core/printer.py:39` | Comment labels LAN creds "(fallback)" — LAN is primary | Relabel |
| L13 | `core/printer.py:487-499` | `send_and_print` docstring contradicts CLAUDE.md | Rewrite (with H4) |
| L14 | `core/printer.py:175` | Redundant `headers={}` kwarg (dead cloud path) | Drop |
| L15 | `core/print_queue.py:160,239,261` | Broadcast failures swallowed with bare `pass` | `log.debug(...)` |
| L16 | `core/smb_watcher.py:32-33` | `lambda` assigned to a name (PEP-8) | Convert to `def` |
| L17 | `api/routes/gallery.py:225-235` | Unused `loop` var; `PIL.Image` imported twice; mid-function imports | Delete `loop`; hoist imports |
| L18 | `core/voice_bridge.py:360-367` | `get_history` skips a trailing unpaired turn; dead `else None` branch | Iterate full range; drop dead branch |
| L19 | `core/voice_bridge.py:98-114,507,556,582,605` | `import httpx` repeated inside functions | Hoist to module top |
| L20 | `core/voice_bridge.py:621-629` | `_emit` builds the coroutine off-loop; failure swallowed | Marshal via a lambda; `log.debug` on failure |
| L21 | `core/voice_bridge.py` history thread-safety | `_history`/`_conversation_id` mutated by the daemon thread, read by HTTP handlers, no lock — low probability, display-only | Guard with a `threading.Lock` |
| L22 | `core/voice_bridge.py:334-339` | `trigger()` TOCTOU — a manual trigger can fire one wake-cycle late | Clear `_manual_trigger` after each turn |
| L23 | `api/routes/settings.py:202` | f-string with no placeholders | Drop the `f` |
| L24 | `api/routes/settings.py:60-61,134,392` | Stale `_read_env` docstring; imports inside functions | Reword; hoist imports |
| L25 | `ha/jarvis_dashboard.yaml:265` | Unresolved `# verify entity ID` note | Verify `climate.main_floor` or remove the card |
| L26 | `ha/jarvis_dashboard.yaml` | Household PII (names, gamertags, MACs) — not app code (verified: no Python reads it) | Remove from repo / sanitise (decision **D6**) |
| L27 | `ui/src/components/PhaseStub.tsx` | Dead component — 0 refs (verified) | Delete; update the stale CLAUDE.md Phase 9 note |
| L28 | `ui/src/components/Console.tsx:4-16` | `LVL_COLOR` / `MSG_COLOR` are identical maps | Delete `MSG_COLOR` |
| L29 | UI misc | `useWebSocket` leaked ping-interval on reconnect & post-unmount reconnect (`:22-69`); `_logId` incremented in render (`:13`); `Layout.tsx:123` hard-codes `http://` (use `location.origin`); stale `PHASE n` page-header labels (`Scanner/Print/Voice/Settings`); `Calibration.tsx:217` RESET `onBlur` (fragile — the pattern already replaced in `Scanner`'s `LibraryCard`); `Settings.tsx:30,56` dev-IP placeholders; `tsconfig.app.json:16-17` `noUnusedLocals/Parameters` disabled | Address as a UI-polish batch; re-enable the `tsc` checks **after** the dead-code deletions land |

---

# Dead / unattached code — zero-impact confirmation

Per the request: each item below was grep-verified across the repo. "Safe" = removal cannot
affect runtime behaviour.

| Item | File | Verification | Safe to remove? |
|---|---|---|---|
| `QUALITY_PROFILES` | `core/slicer.py:49-53` | grep — only the definition, 0 reads | ✅ Yes, zero impact |
| `rolling` buffer | `core/voice_bridge.py:444…469` | All sites are writes/trims; 0 reads | ✅ Yes, zero impact |
| `PhaseStub` | `ui/src/components/PhaseStub.tsx` | grep `ui/src` — 0 refs outside its own file | ✅ Yes, zero impact |
| `fetchScanObject` | `ui/src/api/client.ts:172-174` | grep — 0 callers | ✅ Yes (no UI uses single-object GET) |
| `addManualObject` + `ManualObjectBody` | `ui/src/api/client.ts:127-136,176-182` | grep — 0 callers | ⚠️ Client fn yes; **backend route stays** — decision **D5** |
| `import shutil` | `api/routes/system.py:2` | grep — only the import line | ✅ Yes, zero impact |
| `embedUrl` alias, `iframeRef` | `ui/src/pages/HomeAssistant.tsx:10,16,86` | `iframeRef.current` never read; `embedUrl === haUrl` always | ✅ Yes, zero impact |
| `TurnCard` `index` prop | `ui/src/pages/Voice.tsx:38,237` | `index` never used in the body | ✅ Yes, zero impact |
| `loop` var | `api/routes/gallery.py:234` | Assigned, never used | ✅ Yes, zero impact |
| `MSG_COLOR` | `ui/src/components/Console.tsx:4-16` | Identical to `LVL_COLOR`, same lookup key | ✅ Yes, zero impact |
| `core/printer_lan.py` (whole file) | — | grep — 0 imports repo-wide | ✅ Runtime-safe; keep a git tag first (decision **D2**) |
| `core/bambu_signing.py` (whole file) | — | Used only by the cloud path (`printer.py:249`, lazy) | ⚠️ Safe **iff** the cloud path is also removed — decision **D1** |
| `_cloud_send_and_print` + cloud branch | `core/printer.py:130-275` | Reachable, but unintended (see H4) | ⚠️ Decision **D1** |
| `bambu-lab-cloud-api` dependency | `requirements.txt:14` | grep — never imported (`bambulab`/`bambulabs_api` are used instead) | ✅ Likely removable; confirm with D1 |
| root `test_bambu.py` | — | Standalone script, imported by nothing | ✅ Safe to move/delete (C2/D3) |
| `scripts/test_*.py` | — | Standalone scripts | ✅ Safe to move (D3) |

**Verified NOT dead** (do not remove): `is_valid()` (`core/calibration.py:68` — used by `system.py`), `RadarAnimation` & `BootChecklist` (used by `Dashboard`), all 5 UI hooks, `certs/printer.pem` (a **public** X.509 certificate — verified, not a private key — used for FTPS TLS verification; harmless to keep).

---

# Recommended execution order (Stage 2)

Each batch = one commit (or a small group), referencing the finding IDs, so any batch
is independently revertable.

| Batch | Contents | Risk | Notes |
|---|---|---|---|
| **1 — Secrets** | C1, C2, C3, H2 | Low (config/docs) | + rotate the printer access code (D7). Do first; unblocks a clean release. |
| **2 — Settings security** | C4, C5, H13, H14, H15 | Medium | Touches the auth surface; update `client.ts` in the same batch. |
| **3 — Project-rule violations** | H1, H3 | Low | Forbidden strings + CLAUDE.md carve-out note. |
| **4 — Printer correctness** | H4, M9, M10, C3-cleanup | Medium | **Gated on D1/D2.** The riskiest functional change — test a real print after. |
| **5 — Known bugs** | H6, H7, H10, H11, H12 | Medium | Locks + atomic writes + the two long-standing CLAUDE.md bugs. |
| **6 — Version unification** | H5 | Low | Single source of truth → enables the **1.0 bump**. |
| **7 — UI correctness** | H8, H9, H16, M21–M24 | Low–Medium | Tailwind tokens, XSS sanitiser, dead code. |
| **8 — Maintainability** | M1–M8, M11–M20, M25 | Low–Medium | Dedup/refactor; behaviour-preserving. |
| **9 — Cosmetic** | L1–L29 | Very low | One sweep; re-enable `tsc` unused-checks last. |
| **10 — Release** | Version → `1.0.0`, README, architecture map | — | After batches 1–9 verified. |

**Testing gate:** after batches 4 and 5, run the live print and scan flows on `KJLC-AI-01`
before proceeding — those are the only changes that can break a physical-hardware path.

---

*End of Phase 10 QA Roadmap — Stage 1. No code has been modified. Awaiting review.*
