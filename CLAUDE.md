# Holomat API — Claude Code Context

## Project overview
Holomat is a Raspberry Pi-based smart mat system with a JARVIS-themed React UI.
The backend is a FastAPI server (`main.py`) with phase-gated feature development.
Current live phase: **Phase 4 — Object Scanner**.

## Phase roadmap (for planning reference)
- Phase 0: API scaffold + JARVIS UI bootstrap ✅
- Phase 1: ChArUco calibration engine ✅
- Phase 2: React/Vite UI shell ✅
- Phase 3: Home Assistant MQTT bridge ✅
- Phase 4: Object scanner (CV + Gemini Vision + library) ✅
- Phase 4F: OpenSCAD case generation (Gemini text) ✅
- Phase 5: OpenSCAD → STL compilation
- Phase 6: SMB gallery watcher / HEIC conversion
- Phase 7: Print queue (Bambu P1S)
- Phase 8: Wyoming voice bridge
- Phase 9+: TBD

## AI provider — IMPORTANT
**All AI inference uses Google Gemini, not OpenAI.**
- Vision (object identification): `gemini-1.5-flash` via `google-generativeai`
- Text generation (OpenSCAD case gen): same model
- Env var: `GEMINI_API_KEY`
- Optional model override: `GEMINI_MODEL` (default: `gemini-1.5-flash`)
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

## Known open issues (post Phase 4 review)
- `scan_data/library.json` has no write lock — concurrent requests can race. Add a `threading.Lock` before Phase 5 adds more write paths.
- `height_mm = entry.get("height_mm") or 20.0` in `api/routes/scan.py` treats `0.0` as unset. Use `is not None` check.
- Delete-confirm `onBlur` in `LibraryCard` (Scanner.tsx) resets on mouse-out — fragile UX, fix before user testing.
- `libraryLoading` state is tracked in `useScanner` but not wired to a spinner in `Scanner.tsx`.
