"""
Wyoming protocol bridge — exposes the Cloudflare STT/LLM/TTS workers
as a local Wyoming satellite that Home Assistant can discover.

When running, KJLC-AI-01 appears in HA as a voice assistant media player.
Uses wyoming-satellite (pip package) configured to proxy to:
  STT: https://wyoming-stt.kjeg.workers.dev
  LLM: https://wyoming-llm.kjeg.workers.dev
  TTS: https://wyoming-tts.kjeg.workers.dev

microWakeWord runs locally (TFLite) for "Hey Jarvis" detection at < 5% CPU.

Implemented in Phase 8.
"""
from core.logger import get_logger

log = get_logger(__name__)


class VoiceBridge:
    """Manages the wyoming-satellite subprocess."""

    def __init__(self):
        self._process = None

    def start(self) -> None:
        """Launch wyoming-satellite subprocess. Implemented in Phase 8."""
        raise NotImplementedError("Phase 8")

    def stop(self) -> None:
        """Terminate the satellite subprocess."""
        if self._process:
            self._process.terminate()

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None


voice_bridge = VoiceBridge()
