"""Voice bridge API routes."""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["voice"])


@router.get("/status")
async def get_voice_status():
    from core.voice_bridge import voice_bridge
    return voice_bridge.status()


@router.get("/history")
async def get_voice_history():
    from core.voice_bridge import voice_bridge
    return {
        "turns": voice_bridge.get_history(),
        "conversation_id": voice_bridge._conversation_id,
    }


@router.post("/trigger")
async def trigger_voice():
    """Manually start a voice capture session (equivalent to saying the wake word)."""
    from core.voice_bridge import voice_bridge
    if not voice_bridge.running:
        raise HTTPException(
            status_code=503,
            detail="Voice bridge not running — set WYOMING_ENABLED=true and restart",
        )
    success = voice_bridge.trigger()
    if not success:
        raise HTTPException(
            status_code=409,
            detail=f"Voice bridge busy ({voice_bridge.state}) — wait for idle",
        )
    return {"triggered": True, "state": voice_bridge.state}


@router.delete("/history")
async def clear_voice_history():
    """Clear the LLM conversation history and reset the conversation ID."""
    from core.voice_bridge import voice_bridge
    voice_bridge.clear_history()
    return {"cleared": True}
