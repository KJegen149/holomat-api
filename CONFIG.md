# Holomat — Configuration Reference

Every env var the project reads, grouped by subsystem. Values are loaded at
boot from `.env` (via `python-dotenv`) and the Settings UI rewrites that file
in place when you edit credentials there.

**Notation**
- ✅ **Required** — the relevant feature does not work without it.
- ⚙️ **Optional** — has a sensible default; only set to override.
- 🔐 **Sensitive** — never commit, never log, surfaced as a password input.

---

## 1. Bambu Lab P1S printer

| Var                  | Required? | Default                  | Effect                                                                                              |
|---|---|---|---|
| `BAMBU_SERIAL`       | ✅        | —                        | Printer serial. Appears in MQTT topics: `device/{serial}/request`.                                  |
| `BAMBU_IP`           | ✅        | —                        | Printer's LAN IP. Both FTPS and MQTT connect here.                                                  |
| `BAMBU_ACCESS_CODE`  | ✅ 🔐     | —                        | 8-digit code from the printer's Network settings. **Rotates** when LAN/Cloud mode is toggled.       |
| `BAMBU_EMAIL`        | ✅ 🔐     | —                        | Bambu account email. Used only to look up `user_id` — the LAN MQTT payload requires it.             |
| `BAMBU_PASSWORD`     | ✅ 🔐     | —                        | Bambu account password.                                                                             |
| `BAMBU_AMS_SLOT`     | ⚙️        | `0`                      | Default AMS slot (0–3, or `-1` for external spool). Per-print picker can override.                  |
| `BAMBU_CERT`         | ⚙️        | `certs/printer.pem`      | Path to the FTPS X.509 certificate. The bundled cert is public and works as-is.                     |
| `BAMBU_FTP_PORT`     | ⚙️        | `990`                    | Implicit FTPS port. Don't change unless you know why.                                               |
| `BAMBU_MQTT_PORT`    | ⚙️        | `8883`                   | LAN MQTT TLS port.                                                                                  |
| `BAMBU_REGION`       | ⚙️        | `global`                 | Bambu cloud region for user_id auth. `global` or `china`.                                           |
| `BAMBU_TOKEN_FILE`   | ⚙️        | `scan_data/.bambu_token` | Path where the Bambu cloud session token is cached and refreshed.                                   |

> **Hardware setup:** Developer Mode must be **ON** on the printer touchscreen
> (Settings → Network). LAN-only mode is **not** required — the printer can
> stay cloud-connected so Bambu Handy / Studio keep working alongside Holomat.

---

## 2. Google Gemini (AI provider)

| Var                | Required? | Default               | Effect                                                                                  |
|---|---|---|---|
| `GEMINI_API_KEY`   | ✅ 🔐     | —                     | Required for object identification (Vision) and case generation (text).                 |
| `GEMINI_MODEL`     | ⚙️        | `gemini-2.5-flash`    | Override the model name. Keep on a Flash-tier model — Pro is too slow for live scans.   |

> **Project rule:** All AI inference is on Gemini. Do not introduce
> `OPENAI_API_KEY`, `openai`, or `gpt-*` references anywhere in this project.

---

## 3. Cloudflare Workers (voice + gallery pipeline)

| Var          | Required? | Default | Effect                                                                                     |
|---|---|---|---|
| `CF_API_URL` | ✅        | —       | Base URL of the Cloudflare worker that proxies gallery R2 + Meshy + the voice pipeline.    |
| `CF_API_KEY` | ✅ 🔐     | —       | Bearer token for the worker. Set as the `X-API-Key` header on outbound requests.           |

The worker URLs the **voice pipeline** calls are also overridable (defaults
point at the production deployment):

| Var                  | Default                                       | Effect                       |
|---|---|---|
| `WYOMING_STT_URL`    | `https://wyoming-stt.kjeg.workers.dev`         | Speech-to-text endpoint.     |
| `WYOMING_TTS_URL`    | `https://wyoming-tts.kjeg.workers.dev`         | Text-to-speech endpoint.     |
| `WYOMING_LLM_URL`    | `https://wyoming-llm.kjeg.workers.dev`         | JARVIS LLM endpoint.         |

---

## 4. Home Assistant integration

| Var               | Required? | Default | Effect                                                                                |
|---|---|---|---|
| `HA_URL`          | ⚙️        | —       | HA base URL (e.g. `https://ha.example.com`). Used by the in-UI embed + service calls. |
| `HA_TOKEN`        | ⚙️ 🔐     | —       | Long-lived access token. Needed for voice-driven device control via `/api/services`.  |
| `HA_MQTT_HOST`    | ⚙️        | —       | Mosquitto host. **If unset, the HA bridge does not start.**                           |
| `HA_MQTT_PORT`    | ⚙️        | `1883`  | Mosquitto port.                                                                       |
| `HA_MQTT_USER`    | ⚙️        | —       | MQTT username (anonymous broker allowed).                                             |
| `HA_MQTT_PASS`    | ⚙️ 🔐     | —       | MQTT password.                                                                        |

Setting `HA_MQTT_HOST` alone enables the discovery bridge, which publishes
Holomat as a device in HA. Setting `HA_URL` + `HA_TOKEN` additionally enables
voice-driven HA device control (the LLM emits a `service` field, Holomat hits
HA REST to execute it).

---

## 5. Voice bridge (Phase 8 — Wyoming + wake word)

| Var                          | Required? | Default | Effect                                                                                       |
|---|---|---|---|
| `WYOMING_ENABLED`            | ⚙️        | `false` | Master switch. Set to `true` to start the voice bridge at boot.                              |
| `WYOMING_STT_PORT`           | ⚙️        | `10300` | TCP port the Wyoming STT server listens on (HA dials in here).                               |
| `WYOMING_TTS_PORT`           | ⚙️        | `10200` | TCP port the Wyoming TTS server listens on.                                                  |
| `WYOMING_MIC_INDEX`          | ⚙️        | —       | `sounddevice` input device index. `python -m sounddevice` lists them.                        |
| `WYOMING_SPEAKER_INDEX`      | ⚙️        | —       | `sounddevice` output device index.                                                           |
| `WYOMING_WAKE_SENSITIVITY`   | ⚙️        | `0.5`   | openWakeWord trigger threshold (0–1, higher = stricter).                                     |

> **System dep:** `libportaudio2` must be installed
> (`sudo apt install libportaudio2`) or `sounddevice` fails to import.

---

## 6. Camera + ChArUco calibration

| Var                       | Required? | Default | Effect                                                                          |
|---|---|---|---|
| `CAMERA_DEVICE`           | ⚙️        | `0`     | OpenCV device index. `0` is the first connected camera.                         |
| `CHARUCO_COLS`            | ⚙️        | `7`     | Board column count.                                                             |
| `CHARUCO_ROWS`            | ⚙️        | `5`     | Board row count.                                                                |
| `CHARUCO_SQUARE_MM`       | ⚙️        | `40.0`  | Square edge length in mm.                                                       |
| `CHARUCO_MARKER_MM`       | ⚙️        | `30.0`  | ArUco marker edge length in mm.                                                 |
| `CHARUCO_MIN_CORNERS`     | ⚙️        | `6`     | Minimum corners required to accept a capture.                                   |

Override only if your physical calibration board differs from the bundled
spec — the defaults match the kit Holomat ships with.

---

## 7. Scanner

| Var                          | Required? | Default | Effect                                                                              |
|---|---|---|---|
| `SCAN_DIFF_THRESHOLD`        | ⚙️        | `30`    | Per-pixel grayscale-delta threshold for background subtraction (0–255).             |
| `SCAN_MIN_CONTOUR_AREA`      | ⚙️        | `500`   | Minimum contour area (px²) to consider a contour an object. Filters dust/glare.     |

---

## 8. Slicer tooling

| Var                  | Required?       | Default                  | Effect                                                                       |
|---|---|---|---|
| `OPENSCAD_BIN`       | ⚙️              | `openscad`               | OpenSCAD binary name or absolute path.                                       |
| `OPENSCAD_DISPLAY`   | ⚙️              | inherits `$DISPLAY`      | Override `$DISPLAY` when running as a headless systemd service (e.g. `:99`). |
| `ORCA_CLI`           | ⚙️              | `/usr/bin/orca-slicer`   | OrcaSlicer CLI binary path.                                                  |
| `ORCA_APPIMAGE`      | ⚙️              | —                        | If set, takes precedence over `ORCA_CLI` (preferred for headless installs).  |
| `ORCA_DISPLAY`       | ⚙️              | inherits `$DISPLAY`      | Override `$DISPLAY` for OrcaSlicer (e.g. `:99` for Xvfb).                    |
| `ORCA_PROFILES_DIR`  | ⚙️              | OrcaSlicer's default     | Override the profile root directory.                                         |

OpenSCAD compilation of a typical case `.scad` takes 1–5 seconds on
`KJLC-AI-01`. The 120 s timeout in `core/slicer.py` is generous.

---

## 9. Admin / Settings API auth

| Var                    | Required?          | Default | Effect                                                                  |
|---|---|---|---|
| `HOLOMAT_ADMIN_KEY`    | ⚙️ 🔐 (prod-only)  | —       | Required header value for `/api/settings/*` write endpoints.            |

> If unset, the Settings API endpoints accept any request — fine on a
> kiosk on a trusted LAN, **not** fine if the API is internet-reachable.

---

## 10. Sample `.env`

A minimum config that gets you past the boot checklist:

```env
# AI
GEMINI_API_KEY=...

# Printer (all five are required)
BAMBU_SERIAL=...
BAMBU_IP=10.x.x.x
BAMBU_ACCESS_CODE=12345678
BAMBU_EMAIL=you@example.com
BAMBU_PASSWORD=...

# Cloudflare workers (gallery + Meshy + voice pipeline)
CF_API_URL=https://your-worker.workers.dev
CF_API_KEY=...

# Optional but typical
HA_URL=https://ha.example.com
HA_TOKEN=...
HA_MQTT_HOST=10.x.x.x
WYOMING_ENABLED=true
HOLOMAT_ADMIN_KEY=...
```

The Settings UI (`/settings` in the SPA) renders the same fields with
password masking and a "restart required" banner after edits.
