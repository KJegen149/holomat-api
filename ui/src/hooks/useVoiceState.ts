import { useEffect, useState } from 'react'

/* Voice bridge states, as emitted by core/voice_bridge.py.
   - idle:      waiting for "Hey Jarvis" wake word
   - listening: wake fired, recording user speech
   - thinking:  STT done, LLM working
   - speaking:  TTS playing back the response */
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking'

interface VoiceEvent {
  type?: string
  state?: VoiceState
  text?: string
  speech?: string
}

/* Subscribes to the 'holomat:voice' DOM events that useWebSocket re-broadcasts
   from the backend WS feed. Returns the live state. Multiple components can
   call this hook independently. */
export function useVoiceState(): VoiceState {
  const [state, setState] = useState<VoiceState>('idle')

  useEffect(() => {
    const onVoice = (e: Event) => {
      const detail = (e as CustomEvent<VoiceEvent>).detail
      if (!detail) return
      if (detail.type === 'voice_state_change' && detail.state) {
        setState(detail.state)
      } else if (detail.type === 'voice_ready') {
        setState('idle')
      }
    }
    window.addEventListener('holomat:voice', onVoice)
    return () => window.removeEventListener('holomat:voice', onVoice)
  }, [])

  return state
}
