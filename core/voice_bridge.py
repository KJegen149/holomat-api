"""
JARVIS voice bridge — Phase 8.

Runs two Wyoming protocol TCP servers as asyncio tasks on the shared uvicorn
event loop, and a standalone "Hey Jarvis" voice loop in a daemon thread:

  Wyoming STT :10300 — wraps Cloudflare Whisper worker (HA voice pipeline)
  Wyoming TTS :10200 — wraps Cloudflare Deepgram worker (HA voice pipeline)
  Voice loop  thread — openWakeWord → STT → LLM → TTS → speaker playback

Wyoming servers let Home Assistant use JARVIS STT/TTS for its Assist pipeline.
The standalone loop enables hands-free "Hey Jarvis" independent of HA.

Environment variables:
  WYOMING_ENABLED=true        — must be "true" to activate (default: false)
  WYOMING_STT_PORT=10300      — Wyoming STT server port
  WYOMING_TTS_PORT=10200      — Wyoming TTS server port
  WYOMING_STT_URL             — Cloudflare STT worker URL
  WYOMING_TTS_URL             — Cloudflare TTS worker URL
  WYOMING_LLM_URL             — Cloudflare LLM worker URL
  WYOMING_MIC_INDEX           — sounddevice mic device index (default: system default)
  WYOMING_SPEAKER_INDEX       — sounddevice speaker device index
  WYOMING_WAKE_SENSITIVITY    — openWakeWord threshold 0-1 (default: 0.5)
  HA_TOKEN                    — HA long-lived access token for device state + service calls
"""
import asyncio
import io
import json
import os
import threading
import wave
from typing import Any, Callable

import numpy as np

from core.logger import get_logger

log = get_logger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
_ENABLED          = os.getenv("WYOMING_ENABLED", "false").lower() == "true"
_STT_PORT         = int(os.getenv("WYOMING_STT_PORT") or "10300")
_TTS_PORT         = int(os.getenv("WYOMING_TTS_PORT") or "10200")
_STT_URL          = os.getenv("WYOMING_STT_URL", "https://wyoming-stt.kjeg.workers.dev")
_TTS_URL          = os.getenv("WYOMING_TTS_URL", "https://wyoming-tts.kjeg.workers.dev")
_LLM_URL          = os.getenv("WYOMING_LLM_URL", "https://wyoming-llm.kjeg.workers.dev")
_MIC_INDEX        = os.getenv("WYOMING_MIC_INDEX")
_SPEAKER_INDEX    = os.getenv("WYOMING_SPEAKER_INDEX")
_WAKE_SENSITIVITY = float(os.getenv("WYOMING_WAKE_SENSITIVITY") or "0.5")
_HA_URL           = os.getenv("HA_URL", "").rstrip("/")
_HA_TOKEN         = os.getenv("HA_TOKEN", "")

# Audio constants — openWakeWord requires 16 kHz mono 16-bit, 80 ms chunks
_MIC_RATE     = 16_000
_CHANNELS     = 1
_CHUNK_FRAMES = 1_280      # 80 ms at 16 kHz
_MAX_REC_SEC  = 12
_SILENCE_SEC  = 1.2
_VAD_THRESH   = 300.0      # RMS energy below this = silence


# ── Shared helpers ────────────────────────────────────────────────────────────

def _pcm_to_wav(pcm: bytes, rate: int = _MIC_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _wav_to_pcm(wav_bytes: bytes) -> tuple[bytes, int, int, int]:
    """Returns (raw_pcm, sample_rate, sample_width_bytes, channels)."""
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        return wf.readframes(wf.getnframes()), wf.getframerate(), wf.getsampwidth(), wf.getnchannels()


def _rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def _call_stt(wav_bytes: bytes) -> str:
    """Blocking HTTP call to Cloudflare STT worker."""
    import httpx
    r = httpx.post(_STT_URL, content=wav_bytes, headers={"Content-Type": "audio/wav"}, timeout=15)
    r.raise_for_status()
    return r.json().get("text", "").strip()


def _call_tts(text: str) -> bytes:
    """Blocking HTTP call to Cloudflare TTS worker. Returns WAV bytes."""
    import httpx
    r = httpx.post(_TTS_URL, json={"text": text}, timeout=15)
    r.raise_for_status()
    return r.content


def _call_llm(text: str, history: list, device_list: list, conversation_id: str | None) -> dict:
    """Blocking HTTP call to Cloudflare LLM worker."""
    import httpx
    payload: dict[str, Any] = {"text": text, "history": history, "device_list": device_list}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    r = httpx.post(_LLM_URL, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def _parse_jarvis(raw: str) -> tuple[str, dict | None]:
    """Parse JARVIS JSON {speech, service} from LLM output. Falls back to raw text."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:]).rstrip("`").strip()
    try:
        data = json.loads(raw)
        return data.get("speech", raw), data.get("service") or None
    except json.JSONDecodeError:
        return raw, None


# ── Wyoming STT session ───────────────────────────────────────────────────────

async def _stt_session(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handle one Wyoming STT connection from Home Assistant."""
    from wyoming.event import async_read_event, async_write_event
    from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.asr import Transcribe, Transcript

    wav_buf: io.BytesIO | None = None
    wav_wf = None

    try:
        while True:
            event = await async_read_event(reader)
            if event is None:
                break

            if Describe.is_type(event.type):
                await async_write_event(
                    Info(asr=[AsrProgram(
                        name="jarvis-stt",
                        description="JARVIS STT via Cloudflare (Whisper Large V3 Turbo)",
                        attribution=Attribution(name="JARVIS", url=""),
                        installed=True,
                        models=[AsrModel(
                            name="whisper-large-v3-turbo",
                            description="Whisper Large V3 Turbo via Cloudflare / Groq",
                            attribution=Attribution(name="OpenAI / Groq", url=""),
                            installed=True,
                            languages=["en"],
                        )],
                    )]).event(),
                    writer,
                )

            elif Transcribe.is_type(event.type):
                pass  # language hint — always English; acknowledge silently

            elif AudioStart.is_type(event.type):
                s = AudioStart.from_event(event)
                wav_buf = io.BytesIO()
                wav_wf = wave.open(wav_buf, "wb")
                wav_wf.setnchannels(s.channels)
                wav_wf.setsampwidth(s.width)
                wav_wf.setframerate(s.rate)

            elif AudioChunk.is_type(event.type) and wav_wf is not None:
                wav_wf.writeframes(AudioChunk.from_event(event).audio)

            elif AudioStop.is_type(event.type):
                text = ""
                if wav_wf is not None:
                    wav_wf.close()
                    wav_wf = None
                if wav_buf is not None:
                    wav_bytes = wav_buf.getvalue()
                    wav_buf = None
                    try:
                        text = await asyncio.to_thread(_call_stt, wav_bytes)
                        log.info("Wyoming STT → %r", text[:80])
                    except Exception as exc:
                        log.warning("Wyoming STT call failed: %s", exc)
                await async_write_event(Transcript(text=text).event(), writer)

    except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError):
        pass
    except Exception as exc:
        log.debug("Wyoming STT session error: %s", exc)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── Wyoming TTS session ───────────────────────────────────────────────────────

async def _tts_session(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handle one Wyoming TTS connection from Home Assistant."""
    from wyoming.event import async_read_event, async_write_event
    from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.tts import Synthesize

    try:
        while True:
            event = await async_read_event(reader)
            if event is None:
                break

            if Describe.is_type(event.type):
                await async_write_event(
                    Info(tts=[TtsProgram(
                        name="jarvis-tts",
                        description="JARVIS TTS via Cloudflare (Deepgram Aura-2 Theia)",
                        attribution=Attribution(name="JARVIS", url=""),
                        installed=True,
                        voices=[TtsVoice(
                            name="theia",
                            description="Deepgram Aura-2 Theia — English",
                            attribution=Attribution(name="Deepgram", url=""),
                            installed=True,
                            languages=["en-US"],
                        )],
                    )]).event(),
                    writer,
                )

            elif Synthesize.is_type(event.type):
                synth = Synthesize.from_event(event)
                log.info("Wyoming TTS → %r", synth.text[:80])
                raw, rate, width, channels = b"", 24000, 2, 1
                try:
                    wav_bytes = await asyncio.to_thread(_call_tts, synth.text)
                    raw, rate, width, channels = _wav_to_pcm(wav_bytes)
                except Exception as exc:
                    log.warning("Wyoming TTS call failed: %s", exc)

                await async_write_event(
                    AudioStart(rate=rate, width=width, channels=channels).event(), writer
                )
                chunk_size = 4096
                for i in range(0, len(raw), chunk_size):
                    await async_write_event(
                        AudioChunk(rate=rate, width=width, channels=channels,
                                   audio=raw[i:i + chunk_size]).event(),
                        writer,
                    )
                await async_write_event(AudioStop().event(), writer)

    except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError):
        pass
    except Exception as exc:
        log.debug("Wyoming TTS session error: %s", exc)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── VoiceBridge ───────────────────────────────────────────────────────────────

class VoiceBridge:
    """
    Manages Wyoming STT/TTS servers (asyncio) and the JARVIS voice loop (thread).

    start() is called from the FastAPI lifespan (async context), so it can use
    asyncio.get_running_loop() to schedule the Wyoming server tasks.
    """

    def __init__(self) -> None:
        self._broadcast: Callable | None = None
        self._history: list[dict] = []
        self._conversation_id: str | None = None
        self._stop_event = threading.Event()
        self._manual_trigger = threading.Event()
        self._thread: threading.Thread | None = None
        self._stt_task: asyncio.Task | None = None
        self._tts_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.running = False
        self.state = "idle"

    # ── Public API ────────────────────────────────────────────────────────────

    def set_broadcast(self, fn: Callable) -> None:
        self._broadcast = fn

    def start(self) -> None:
        if not _ENABLED:
            raise NotImplementedError("Phase 8 — set WYOMING_ENABLED=true to activate voice bridge")

        self._loop = asyncio.get_running_loop()
        self._stop_event.clear()

        # Wyoming servers as asyncio background tasks (share uvicorn's event loop)
        self._stt_task = self._loop.create_task(self._run_stt_server(), name="wyoming-stt")
        self._tts_task = self._loop.create_task(self._run_tts_server(), name="wyoming-tts")

        # Voice loop in a daemon thread (sounddevice is blocking I/O)
        self._thread = threading.Thread(target=self._voice_loop, daemon=True, name="voice-bridge")
        self._thread.start()

        self.running = True
        log.info("Voice bridge started — Wyoming STT :%d, TTS :%d", _STT_PORT, _TTS_PORT)

    def stop(self) -> None:
        self._stop_event.set()
        if self._stt_task:
            self._stt_task.cancel()
        if self._tts_task:
            self._tts_task.cancel()
        self.running = False
        self.state = "idle"

    def trigger(self) -> bool:
        """Manually start voice capture (as if wake word was detected)."""
        if not self.running or self.state != "idle":
            return False
        self._manual_trigger.set()
        return True

    def clear_history(self) -> None:
        self._history.clear()
        self._conversation_id = None

    def status(self) -> dict:
        return {
            "running": self.running,
            "state": self.state,
            "stt_url": _STT_URL,
            "tts_url": _TTS_URL,
            "llm_url": _LLM_URL,
            "stt_port": _STT_PORT,
            "tts_port": _TTS_PORT,
            "wake_sensitivity": _WAKE_SENSITIVITY,
            "ha_integration": bool(_HA_TOKEN),
            "history_turns": len(self._history) // 2,
            "conversation_id": self._conversation_id,
        }

    def get_history(self) -> list[dict]:
        turns = []
        for i in range(0, len(self._history) - 1, 2):
            user_msg = self._history[i]
            asst_msg = self._history[i + 1] if i + 1 < len(self._history) else None
            speech, _ = _parse_jarvis(asst_msg["content"]) if asst_msg else ("", None)
            turns.append({"user": user_msg["content"], "jarvis": speech})
        return turns

    # ── Wyoming server coroutines ─────────────────────────────────────────────

    async def _run_stt_server(self) -> None:
        try:
            import wyoming  # noqa: F401 — verify package installed
        except ImportError:
            log.warning("wyoming package not installed — Wyoming STT skipped (pip install wyoming)")
            return
        server = await asyncio.start_server(_stt_session, "0.0.0.0", _STT_PORT)
        log.info("Wyoming STT server on :%d", _STT_PORT)
        try:
            async with server:
                await server.serve_forever()
        except asyncio.CancelledError:
            pass

    async def _run_tts_server(self) -> None:
        try:
            import wyoming  # noqa: F401
        except ImportError:
            log.warning("wyoming package not installed — Wyoming TTS skipped (pip install wyoming)")
            return
        server = await asyncio.start_server(_tts_session, "0.0.0.0", _TTS_PORT)
        log.info("Wyoming TTS server on :%d", _TTS_PORT)
        try:
            async with server:
                await server.serve_forever()
        except asyncio.CancelledError:
            pass

    # ── Standalone voice loop ─────────────────────────────────────────────────

    def _voice_loop(self) -> None:
        try:
            import sounddevice as sd
        except ImportError:
            log.error("sounddevice not installed — voice loop disabled (pip install sounddevice)")
            return

        try:
            import openwakeword
            from openwakeword.model import Model as WakeModel
            try:
                openwakeword.utils.download_models()
            except Exception as exc:
                log.warning("Wake word model download warning: %s", exc)
            wakemodel = WakeModel(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        except ImportError:
            log.error("openwakeword not installed — voice loop disabled (pip install openwakeword)")
            return
        except Exception as exc:
            log.error("Failed to load wake word model: %s", exc)
            return

        mic_idx = int(_MIC_INDEX) if _MIC_INDEX else None
        log.info("Voice loop ready — listening for 'Hey Jarvis'")
        self._set_state("idle")
        self._emit("voice_ready", {"message": "Listening for 'Hey Jarvis'"})

        try:
            with sd.InputStream(
                samplerate=_MIC_RATE,
                channels=_CHANNELS,
                dtype="int16",
                blocksize=_CHUNK_FRAMES,
                device=mic_idx,
            ) as stream:
                rolling: list[np.ndarray] = []
                while not self._stop_event.is_set():
                    chunk, _ = stream.read(_CHUNK_FRAMES)
                    chunk = chunk.flatten()
                    rolling.append(chunk)

                    # Rolling 3-second buffer for wake word context
                    max_frames = 3 * _MIC_RATE // _CHUNK_FRAMES + 1
                    if len(rolling) > max_frames:
                        rolling.pop(0)

                    predictions = wakemodel.predict(chunk)
                    detected = any(v >= _WAKE_SENSITIVITY for v in predictions.values())

                    if detected or self._manual_trigger.is_set():
                        self._manual_trigger.clear()
                        log.info("Wake word detected — recording command")
                        self._set_state("listening")
                        self._emit("wake_detected", {})
                        wakemodel.reset()

                        audio = self._record_command(stream)
                        if audio is not None and audio.size > 0:
                            self._process_command(audio)

                        rolling.clear()
                        self._set_state("idle")

        except Exception as exc:
            log.error("Voice loop error: %s", exc)
        finally:
            self.running = False

    def _record_command(self, stream) -> np.ndarray | None:
        """Record speech from stream until trailing silence or max duration."""
        max_frames = _MAX_REC_SEC * _MIC_RATE // _CHUNK_FRAMES
        silence_needed = int(_SILENCE_SEC * _MIC_RATE / _CHUNK_FRAMES)
        frames: list[np.ndarray] = []
        consecutive_silence = 0
        speech_started = False

        for _ in range(max_frames):
            if self._stop_event.is_set():
                return None
            chunk, _ = stream.read(_CHUNK_FRAMES)
            chunk = chunk.flatten()
            frames.append(chunk)

            if _rms(chunk) > _VAD_THRESH:
                speech_started = True
                consecutive_silence = 0
            elif speech_started:
                consecutive_silence += 1
                if consecutive_silence >= silence_needed:
                    break

        if not speech_started:
            log.debug("No speech detected after wake word")
            return None
        return np.concatenate(frames)

    def _process_command(self, audio: np.ndarray) -> None:
        """Full pipeline: STT → LLM → (HA service) → TTS → playback."""
        import httpx
        try:
            # STT
            self._set_state("thinking")
            wav_bytes = _pcm_to_wav(audio.astype(np.int16).tobytes())
            text = _call_stt(wav_bytes)
            if not text:
                log.warning("STT returned empty transcript")
                return
            log.info("JARVIS heard: %r", text)
            self._emit("transcript", {"text": text})

            # LLM
            devices = self._fetch_ha_devices()
            llm_data = _call_llm(text, self._history, devices, self._conversation_id)
            self._conversation_id = llm_data.get("conversation_id")
            raw_text = llm_data.get("text", "")
            speech, service = _parse_jarvis(raw_text)
            if not speech:
                speech = raw_text
            log.info("JARVIS says: %r", speech[:80])
            self._emit("response", {"speech": speech, "service": service})

            # Update history — keep last 10 turns (20 messages)
            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": raw_text})
            if len(self._history) > 20:
                self._history = self._history[-20:]

            # HA service execution
            if service:
                self._execute_ha_service(service)

            # TTS + playback
            self._set_state("speaking")
            tts_wav = _call_tts(speech)
            self._play_wav(tts_wav)

        except httpx.HTTPError as exc:
            log.error("Voice pipeline HTTP error: %s", exc)
            self._emit("error", {"message": str(exc)})
        except Exception as exc:
            log.error("Voice pipeline error: %s", exc)
            self._emit("error", {"message": str(exc)})

    def _fetch_ha_devices(self) -> list[dict]:
        if not _HA_URL or not _HA_TOKEN:
            return []
        try:
            import httpx
            _ALLOWED = {"light", "switch", "climate", "cover", "fan", "media_player", "lock", "input_boolean"}
            r = httpx.get(
                f"{_HA_URL}/api/states",
                headers={"Authorization": f"Bearer {_HA_TOKEN}"},
                timeout=5,
            )
            r.raise_for_status()
            return [
                {
                    "entity_id": e["entity_id"],
                    "name": e.get("attributes", {}).get("friendly_name", e["entity_id"]),
                    "state": e["state"],
                }
                for e in r.json()
                if e["entity_id"].split(".")[0] in _ALLOWED
            ]
        except Exception as exc:
            log.debug("HA device fetch failed: %s", exc)
            return []

    def _execute_ha_service(self, service: dict) -> None:
        if not _HA_URL or not _HA_TOKEN:
            log.warning("HA service skipped — set HA_TOKEN to enable device control")
            return
        try:
            import httpx
            domain = service.get("domain", "")
            svc = service.get("service", "")
            entity_id = service.get("entity_id", "")
            data: dict = dict(service.get("data") or {})
            if entity_id:
                data["entity_id"] = entity_id
            r = httpx.post(
                f"{_HA_URL}/api/services/{domain}/{svc}",
                headers={"Authorization": f"Bearer {_HA_TOKEN}"},
                json=data,
                timeout=10,
            )
            if r.status_code in (200, 201):
                log.info("HA service executed: %s.%s(%s)", domain, svc, entity_id)
                self._emit("ha_service", {"domain": domain, "service": svc, "entity_id": entity_id})
            else:
                log.warning("HA service %s.%s failed %d: %s", domain, svc, r.status_code, r.text[:200])
        except Exception as exc:
            log.error("HA service call error: %s", exc)

    def _play_wav(self, wav_bytes: bytes) -> None:
        try:
            import sounddevice as sd
            raw, rate, width, _ = _wav_to_pcm(wav_bytes)
            dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
            audio = np.frombuffer(raw, dtype=dtype_map.get(width, np.int16))
            speaker_idx = int(_SPEAKER_INDEX) if _SPEAKER_INDEX else None
            sd.play(audio, samplerate=rate, device=speaker_idx)
            sd.wait()
        except Exception as exc:
            log.error("TTS playback failed: %s", exc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_state(self, state: str) -> None:
        self.state = state
        self._emit("state_change", {"state": state})

    def _emit(self, event: str, data: dict) -> None:
        if self._broadcast and self._loop:
            payload = json.dumps({"type": f"voice_{event}", **data})
            try:
                self._loop.call_soon_threadsafe(
                    self._loop.create_task, self._broadcast(payload)
                )
            except Exception:
                pass


voice_bridge = VoiceBridge()
