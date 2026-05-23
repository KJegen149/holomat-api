# Holomat API — Claude Code Context

## Project overview
Holomat is a smart mat system with a JARVIS-themed React UI.
The backend is a FastAPI server (`main.py`) shipped as **version 1.0.0**.
Phases 0–10 are complete; the current focus is the Phase 11 roadmap
(see `PHASE_11_ROADMAP.md`).

> **For human-facing docs see [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md),
> and [CONFIG.md](CONFIG.md).** This file is the AI-context layer — it captures
> non-obvious knowledge, project rules, and known traps that are not
> re-derivable from reading the code.

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
- Phase 6: SMB gallery watcher / HEIC conversion ✅
- Phase 7: Print queue (Bambu P1S) ✅
- Phase 8: Wyoming voice bridge ✅
- Phase 9: Settings UI ✅
- Phase 10: QA pass + 1.0 release ✅
- Phase 11: see `PHASE_11_ROADMAP.md`

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

## Phase 7 implementation notes (Bambu P1S print queue) — CONFIRMED working end-to-end
Full LAN pipeline verified on `KJLC-AI-01` → P1S (firmware 01.08.00, Developer Mode ON,
cloud-connected): queue → slice → FTP upload → MQTT `project_file` → printer ACKs
`result: "success"` → physical print starts (heating, AMS pick, layer 1). Same path
also works on firmware 01.08.02.

**Non-obvious behaviour to keep in mind when editing `core/printer.py` or `core/print_queue.py`:**

- **LAN-only mode is NOT required.** LAN MQTT works on a cloud-connected printer as long as Developer Mode is ON. Bambu Handy / Bambu Studio keep working alongside Holomat. Don't reintroduce a "must be in LAN-only mode" assumption.
- **The cloud print path was DELETED in 1.0.** `_cloud_send_and_print`, `bambu_signing.py`, `bambu_acs_key.py`, and `printer_lan.py` (archive copy) are gone. Reason: the `bambulab` library doesn't expose the project-registration step the printer requires, and LAN works reliably. If a future Claude is asked to "add cloud printing", the right answer is to reverse-engineer the missing project-create call against Bambu Studio — not to revive the old code.
- **`_get_bambu_client()` and `_get_user_id()` survived the cull** — the LAN MQTT payload still needs a valid `user_id` or the printer ACKs success then silently aborts. The only remaining purpose of `BAMBU_EMAIL` + `BAMBU_PASSWORD` is to fetch this `user_id`.
- **Critical URL format:** `file:///sdcard/cache/{filename}` — NOT `ftp:///cache/`. The `ftp://` scheme is X1C-only; P1S silently no-ops with `result:success` but never starts.
- **MQTT lock (`_PRINTER_MQTT_LOCK` in `core/printer.py`):** serialises status polls and the trigger publish. Without it, a concurrent status poll holds the broker connection and the `project_file` publish never reaches the printer (manifests as "FTP OK but no print"). Don't remove it.
- **`PrinterAuthError`** (subclass of `RuntimeError`) is raised for stale `BAMBU_ACCESS_CODE` (MQTT rc=4/5) and OTP-needed Bambu cloud auth. The message is surfaced verbatim in the Print tab's failed-job error field — keep it instruction-shaped, not stack-trace-shaped.
- **Per-job AMS slot picker:** `print_queue.add_job(..., ams_slot=...)` accepts `None` (= use `BAMBU_AMS_SLOT` env default), `-1` (external spool), or `0..3` (AMS trays). Flows into both the slicer's `M620` G-code and the MQTT trigger's `ams_mapping` field.
- **Poll loop semantics:** the queue worker requires seeing `RUNNING`/`PRINTING` at least once before treating `IDLE`/`FINISH` as completion. Without this guard the first poll catches the printer mid-heat and falsely marks the job done in ~10 s. If `RUNNING` is never observed within the startup grace window (~5 min) the job is marked failed with a "silently aborted — check touchscreen" reason.
- **"Done" still means dispatch+complete poll cycle, not physical inspection.** The printer touchscreen remains the ground truth for "is the print actually fine right now".
- **`BAMBU_ACCESS_CODE` rotates** when the printer toggles between LAN/Cloud mode in its own settings. Stale codes surface as `PrinterAuthError`; the user fixes it in the Settings UI.
- **Panda Touch (BTT):** WiFi-only device, USB is charging only. Has NO HTTP control API — all non-root HTTP responses are ESP32 catch-all 500s. Useful as a touchscreen upgrade only.

Working `.env` shape:
```
BAMBU_IP=<lan ip>
BAMBU_ACCESS_CODE=<8-digit code from printer Settings → Network>
BAMBU_SERIAL=<printer serial>
BAMBU_EMAIL=<bambu account email>     # required for user_id lookup
BAMBU_PASSWORD=<bambu account password>
```
(`BAMBU_USE_CLOUD` no longer exists — removed with the cloud path.)

## Phase 9 implementation notes (Settings UI)
- **Backend:** `GET /api/settings` + `POST /api/settings` — reads/writes `.env` file directly. `POST /api/settings/restart` clean-exits the process so systemd respawns.
- **Auth:** writes are gated by `HOLOMAT_ADMIN_KEY` (header). On a kiosk on a trusted LAN, leaving it unset is acceptable.
- **UI:** grouped credential forms (Printer, Gemini, Home Assistant, Cloudflare, Hardware, Voice). Sensitive fields render as `<input type="password">` and show `••••••` if already set — only overwritten if the user types a new value.
- **Connection tests** (`GET /api/settings/test/*`) — Meshy, Bambu, Cloudflare, HA each have a probe endpoint that confirms credentials work without committing a real action.
- **`/api/settings/bambu-auth`** — handles the Bambu cloud OTP challenge. If the cloud auth raises an OTP-needed error during `_get_user_id`, the UI surfaces a prompt; the user enters the code from Bambu Handy and this endpoint completes the token exchange.
- **On-screen keyboard** (`OnScreenKeyboard.tsx`) — the kiosk is touchscreen; this component pops up for text inputs that need a real keyboard.
- **Restart-required banner** — shown after credential changes since the running process holds the old env values.

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

## Phase 10 — QA pass + 1.0 release (DONE)
Full audit landed across 75 findings (C1–C5, H1–H16, M1–M25, L1–L29). See
`PHASE_10_QA_ROADMAP.md` for the per-finding index; each fix commit references
the finding ID so individual changes are revertable.

Top-level outcomes worth knowing for future edits:
- **Settings API** now requires `HOLOMAT_ADMIN_KEY` on write endpoints.
- **`.env` writes** are atomic (tmpfile + rename) and use `python-dotenv`'s parser.
- **Secrets** were scrubbed from history-adjacent files (`.env.example`, `test_bambu.py`, the systemd unit).
- **Gallery SVG** is sanitised before rendering — `dangerouslySetInnerHTML` no longer accepts raw remote SVG.
- **Version** is unified — `core/version.py` is the single source of truth; the UI's `package.json`, the systemd unit description, etc. all read `1.0.0`.
- **Dead code**: `core/printer_lan.py`, `bambu_signing.py`, `bambu_acs_key.py`, `_cloud_send_and_print`, `PhaseStub`, `addManualObject` client fn (route kept), `QUALITY_PROFILES`, `import shutil` in `system.py`, `MSG_COLOR` map duplicate, `voice_bridge.rolling` buffer — all deleted.
- **Maintainability**: the high-value M-tier items landed (M4, M14, M22, L10). The rest of M1–M25 + L1–L29 are cosmetic and tracked but not blocking.

Partial / deferred (not blockers):
- M-tier dedup work outside the high-value subset.
- L-tier cosmetic items (stale docstrings, dead imports, hoisting in-function imports).
- D3 — moving `scripts/test_*.py` to `tools/`.
- D5 — `addManualObject` UI (backend route exists; product call needed first).

## Known open issues (legacy, post-Phase-4)
Most of the original Phase-4 issue list was resolved in Phase 10. What remains:
- ~~`scan_data/library.json` has no write lock~~ — **fixed** (H6, threading.Lock added).
- ~~`height_mm = entry.get("height_mm") or 20.0` treats `0.0` as unset~~ — **fixed** (H7, `is not None` check).
- Delete-confirm `onBlur` in `LibraryCard` (Scanner.tsx) resets on mouse-out — fragile UX, fix before user testing. *(Still open — L29 sub-item.)*
- `libraryLoading` state is tracked in `useScanner` but not wired to a spinner in `Scanner.tsx`. *(Still open — UI polish.)*
