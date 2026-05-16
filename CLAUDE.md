# Holomat API — Claude Code Context

## Project overview
Holomat is a smart mat system with a JARVIS-themed React UI.
The backend is a FastAPI server (`main.py`) with phase-gated feature development.
Current live phase: **Phase 8 — Wyoming Voice Bridge**.

## Hardware topology — IMPORTANT
**There is no Raspberry Pi running the Holomat application.** Do not assume ARM/Pi hardware.

| Host | Role | OS |
|---|---|---|
| `KJLC-AI-01` | Primary host — runs ALL local services: FastAPI backend, camera, projector, OpenSCAD, OrcaSlicer, Bambu print queue, Wyoming voice bridge | Ubuntu 24.04 x86_64 |
| Raspberry Pi 5 | Home Assistant only — accessed via MQTT over LAN | — |

All performance estimates (compile times, timeout values, memory budgets) should be based on `KJLC-AI-01` (gaming laptop, Ubuntu 24.04), not embedded ARM hardware. OpenSCAD compilation of a simple case `.scad` takes **1–5 seconds** on this host.

## Phase roadmap (for planning reference)
- Phase 0: API scaffold + JARVIS UI bootstrap ✅
- Phase 1: ChArUco calibration engine ✅
- Phase 2: React/Vite UI shell ✅
- Phase 3: Home Assistant MQTT bridge ✅
- Phase 4: Object scanner (CV + Gemini Vision + library) ✅
- Phase 4F: OpenSCAD case generation (Gemini text) ✅
- Phase 5: OpenSCAD → STL compilation ✅
- Phase 6: SMB gallery watcher / HEIC conversion
- Phase 7: Print queue (Bambu P1S) ✅
- Phase 8: Wyoming voice bridge ✅
- Phase 9: Settings UI (see notes below)

## AI provider — IMPORTANT
**All AI inference uses Google Gemini, not OpenAI.**
- Vision (object identification): `gemini-2.5-flash` via `google-generativeai`
- Text generation (OpenSCAD case gen): same model
- Env var: `GEMINI_API_KEY`
- Optional model override: `GEMINI_MODEL` (default: `gemini-2.5-flash`)
- Do NOT introduce `openai`, `gpt-*`, or `OPENAI_API_KEY` anywhere in this project.

## Key architectural decisions
- Single process, single camera (`core/camera.py` singleton). Camera stays open between scans — this is intentional; the MJPEG stream shares the same device handle.
- Object library persisted as JSON (`scan_data/library.json`), max 50 entries, FIFO eviction with pin protection.
- Background frame stored as numpy array (`scan_data/background.npy`), identified by mtime.
- `_generate_case_openscad` lives in `api/routes/generate.py` and is shared via direct import into `api/routes/scan.py`. If a third caller appears, move it to `core/`.
- All async camera calls use `asyncio.get_running_loop()` (not deprecated `get_event_loop()`).

## Tech stack
- Backend: Python 3.11+, FastAPI, OpenCV, NumPy, paho-mqtt, google-generativeai
- Frontend: React 18, TypeScript, Vite, Tailwind CSS (`j-*` color namespace), Lucide icons
- 3D printer: Bambu P1S via bambulabs-api + MQTT
- Home Assistant: MQTT discovery bridge (`core/ha_bridge.py`)

## Phase 5 implementation notes
- `core/slicer.compile_openscad()`: async subprocess, `--backend=manifold --export-format binstl`, 120 s timeout.
- STL files persist to `scan_data/stls/`, named `{safe_name}_{8-hex}.stl`.
- `OPENSCAD_DISPLAY` env var overrides `$DISPLAY` if the server runs as a headless systemd service.
- `slice_model()` stub moved to Phase 7 marker (was incorrectly marked Phase 5).
- New routes: `POST /api/generate/openscad`, `GET /api/generate/stl/{filename}`, `POST /api/generate/compile-case`.

## Phase 7 implementation notes (Bambu P1S print queue)
- Printer runs firmware **01.08.02**, **LAN-only mode**, **Developer Mode ON**.
- Print dispatch: FTPS upload (port 990, implicit TLS) → LAN MQTT `project_file` command (port 8883).
- Critical URL format: `file:///sdcard/cache/{filename}` — NOT `ftp:///cache/`. The `ftp://` scheme is X1C-only; P1S silently no-ops with `result:success` but never starts.
- `user_id` is mandatory in the MQTT payload. Without it the printer accepts the command then immediately aborts (shows "incoming 3MF" then "Finished" with no physical action). Fetched via `_get_user_id()` which authenticates with Bambu cloud using `BAMBU_EMAIL` + `BAMBU_PASSWORD`.
- Panda Touch (BTT): WiFi-only device, USB is charging only. Has NO HTTP control API — all non-root HTTP responses are ESP32 catch-all 500s. Useful as a touchscreen upgrade only.
- Cloud MQTT path preserved in `_cloud_send_and_print()` but not the active path — printer is in LAN-only mode.
- LAN archive: `core/printer_lan.py` is a full copy of the working LAN implementation before cloud additions (rollback reference).
- ACS signing: `core/bambu_signing.py` — RSA-SHA256 with community-extracted Bambu Connect key. Required for cloud MQTT path only; LAN MQTT does not need signing.
- `.env` loaded automatically at startup via `python-dotenv`. `BAMBU_ACCESS_CODE` changes each time printer switches between cloud/LAN mode.
- Print queue worker: `core/print_queue.py` — job lifecycle: queued → slicing → uploading → printing → done/failed/cancelled. Persists to `scan_data/print_queue.json`.

## Phase 7 — PENDING: final end-to-end test (revisit after Phase 9)
*Phase 7 code is complete and merged to master. Full pipeline was confirmed working mid-session (AUTO-STARTED ✓) but final CLI test at close of session did not print. Revisit after Phase 9 Settings UI is live so credentials are properly persisted.*

Likely causes to investigate on return:
- `BAMBU_ACCESS_CODE` may have rotated — verify current code on printer (Settings → Network)
- `.env` does not exist on the laptop yet — created only in dev environment. Either create it manually or let Phase 9 Settings write it.
- Bambu cloud auth (`_get_user_id`) may require MFA/OTP — check if `BAMBU_EMAIL`+`BAMBU_PASSWORD` alone is sufficient or if token cache needs priming first (run `scripts/test_bambu_print.py` and watch for auth errors in output)
- The systemd override `override.conf` may have stale `BAMBU_ACCESS_CODE` — check with `sudo systemctl cat holomat-api`

## Phase 9 implementation notes (Settings UI) — planned scope
*Confirmed in Phase 7 chat — implement in Phase 9 chat.*
- Backend: `GET /api/settings` + `POST /api/settings` — reads/writes `.env` file directly.
- UI: grouped credential forms — Printer, Gemini, Home Assistant, Cloudflare, Hardware.
- Sensitive fields (passwords, API keys): render as password inputs, show `••••••` if already set, only overwrite if user types a new value.
- Show "restart required" banner after credential changes (backend needs restart to re-read env).
- Slicer profile editor already exists in Print tab — skip in Settings.
- ChArUco geometry overrides and system diagnostics/log export are lower priority — add if time permits.
- Stub already exists at `ui/src/pages/Settings.tsx` (currently a `PhaseStub` component).

## Phase 8 implementation notes (Wyoming voice bridge)

### Architecture
- **Wyoming STT server** on `:10300` — asyncio TCP server, shares uvicorn event loop via `create_task`.
- **Wyoming TTS server** on `:10200` — same pattern.
- **Standalone voice loop** — daemon thread using `openWakeWord` (ONNX, x86_64 native) + `sounddevice`.
- Wyoming protocol: JSONL-framed events over raw TCP. HA connects TO our server (we listen, HA dials in).
- `wyoming-satellite` package is **archived/deprecated** — DO NOT use. Use `wyoming` core library directly.

### Cloudflare workers (existing, confirmed)
- STT: `POST https://wyoming-stt.kjeg.workers.dev` — audio/wav body → `{text, provider}` JSON
- TTS: `POST https://wyoming-tts.kjeg.workers.dev` — `{text}` JSON body → WAV audio (24 kHz, 16-bit, mono, Deepgram Aura-2 Theia voice)
- LLM: `POST https://wyoming-llm.kjeg.workers.dev` — `{text, history, device_list, conversation_id}` → `{text, conversation_id, model}` where `text` is JARVIS JSON `{speech, service}`

### Wake word
- Model: `hey_jarvis` from openWakeWord built-in models (auto-downloaded on first start).
- `inference_framework="onnx"` — runs on x86_64 without TFLite; ONNX runtime included in openwakeword.
- Chunk size: **1,280 samples = 80 ms at 16 kHz** — required by openWakeWord.

### HA integration
- Add **Wyoming Protocol** integration in HA (Settings → Devices & Services → Add → Wyoming Protocol).
- Point it at `KJLC-AI-01_IP:10300` for STT and `KJLC-AI-01_IP:10200` for TTS.
- Discovery: manual (no Zeroconf implemented — add `wyoming[zeroconf]` if auto-discovery is desired).
- For device control via JARVIS voice: set `HA_TOKEN` to a HA long-lived access token.

### Key env vars (all optional; WYOMING_ENABLED=true required to activate)
- `WYOMING_ENABLED=true` — activate voice bridge
- `WYOMING_STT_PORT=10300` — Wyoming STT port
- `WYOMING_TTS_PORT=10200` — Wyoming TTS port
- `WYOMING_MIC_INDEX` / `WYOMING_SPEAKER_INDEX` — sounddevice device indices
- `WYOMING_WAKE_SENSITIVITY=0.5` — openWakeWord threshold
- `HA_TOKEN` — HA long-lived access token (for `GET /api/states` and `POST /api/services/*`)

### API routes
- `GET  /api/voice/status` — bridge status, state, config
- `GET  /api/voice/history` — conversation turns (user + JARVIS speech)
- `POST /api/voice/trigger` — manual trigger (equivalent to saying "Hey Jarvis")
- `DELETE /api/voice/history` — clear conversation history

### System dependency
- `sounddevice` requires PortAudio: `sudo apt install libportaudio2`
- Mic/speaker must be available on KJLC-AI-01 (gaming laptop has built-in audio)
- Systemd service may need `--user` audio access or `audio` group membership

## Known open issues (post Phase 4 review)
- `scan_data/library.json` has no write lock — concurrent requests can race. Add a `threading.Lock` before Phase 5 adds more write paths.
- `height_mm = entry.get("height_mm") or 20.0` in `api/routes/scan.py` treats `0.0` as unset. Use `is not None` check.
- Delete-confirm `onBlur` in `LibraryCard` (Scanner.tsx) resets on mouse-out — fragile UX, fix before user testing.
- `libraryLoading` state is tracked in `useScanner` but not wired to a spinner in `Scanner.tsx`.
