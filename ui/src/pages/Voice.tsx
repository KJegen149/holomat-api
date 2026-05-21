import { useEffect, useState, useCallback } from 'react'
import { Mic, MicOff, Radio, Loader2, Trash2 } from 'lucide-react'
import {
  fetchVoiceStatus,
  fetchVoiceHistory,
  triggerVoice,
  clearVoiceHistory,
  type VoiceStatus,
  type VoiceTurn,
} from '../api/client'

const STATE_LABEL: Record<string, string> = {
  idle:      'STANDBY',
  listening: 'LISTENING',
  thinking:  'PROCESSING',
  speaking:  'SPEAKING',
}

const STATE_COLOR: Record<string, string> = {
  idle:      'text-j-muted',
  listening: 'text-j-cyan',
  thinking:  'text-j-amber',
  speaking:  'text-j-green',
}

function StateDot({ state }: { state: string }) {
  const pulse = state !== 'idle'
  return (
    <span className={`inline-block w-2 h-2 rounded-full mr-2 ${
      state === 'idle'      ? 'bg-j-muted' :
      state === 'listening' ? 'bg-j-cyan animate-pulse' :
      state === 'thinking'  ? 'bg-j-amber animate-pulse' :
                              'bg-j-green animate-pulse'
    }`} />
  )
}

function TurnCard({ turn, index }: { turn: VoiceTurn; index: number }) {
  return (
    <div className="border border-j-border rounded-sm overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-3 bg-j-bg">
        <span className="text-j-cdim font-mono text-[10px] tracking-[0.15em] uppercase mt-0.5 flex-shrink-0">
          YOU
        </span>
        <p className="text-j-text font-mono text-[12px] leading-relaxed">{turn.user}</p>
      </div>
      <div className="flex items-start gap-3 px-4 py-3 bg-j-surf border-t border-j-border">
        <span className="text-j-cyan font-mono text-[10px] tracking-[0.15em] uppercase mt-0.5 flex-shrink-0">
          JARVIS
        </span>
        <p className="text-j-text font-mono text-[12px] leading-relaxed">{turn.jarvis}</p>
      </div>
    </div>
  )
}

export default function Voice() {
  const [status, setStatus]   = useState<VoiceStatus | null>(null)
  const [turns, setTurns]     = useState<VoiceTurn[]>([])
  const [error, setError]     = useState<string | null>(null)
  const [triggering, setTriggering] = useState(false)
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([fetchVoiceStatus(), fetchVoiceHistory()])
      setStatus(s)
      setTurns(h.turns)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load voice status')
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 2000)
    return () => clearInterval(id)
  }, [refresh])

  const handleTrigger = async () => {
    setTriggering(true)
    setTriggerMsg(null)
    try {
      await triggerVoice()
      setTriggerMsg('Listening...')
    } catch (e) {
      setTriggerMsg(e instanceof Error ? e.message : 'Trigger failed')
    } finally {
      setTriggering(false)
      setTimeout(() => setTriggerMsg(null), 4000)
    }
  }

  const handleClear = async () => {
    try {
      await clearVoiceHistory()
      setTurns([])
    } catch { /* ignore */ }
  }

  const state = status?.state ?? 'idle'
  const running = status?.running ?? false

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel — status + trigger */}
      <div className="w-72 flex-shrink-0 border-r border-j-border bg-j-surf flex flex-col overflow-y-auto">
        <div className="px-5 py-4 border-b border-j-border">
          <div className="flex items-center gap-2 mb-1">
            <Radio size={14} className="text-j-cyan" strokeWidth={1.5} />
            <span className="text-j-cyan font-mono text-[11px] tracking-[0.2em] uppercase">
              Voice Bridge
            </span>
          </div>
        </div>

        {/* Status indicator */}
        <div className="px-5 py-4 border-b border-j-border">
          <div className="flex items-center justify-between mb-3">
            <span className="text-j-muted font-mono text-[10px] tracking-[0.15em] uppercase">Status</span>
            <span className={`font-mono text-[10px] tracking-[0.15em] uppercase ${running ? 'text-j-green' : 'text-j-muted'}`}>
              {running ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>

          <div className="flex items-center">
            <StateDot state={state} />
            <span className={`font-mono text-[11px] tracking-[0.15em] uppercase ${STATE_COLOR[state] ?? 'text-j-muted'}`}>
              {STATE_LABEL[state] ?? state.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Trigger button */}
        <div className="px-5 py-4 border-b border-j-border">
          <button
            onClick={handleTrigger}
            disabled={!running || state !== 'idle' || triggering}
            className={`w-full flex items-center justify-center gap-2 py-3 px-4 rounded-sm
              font-mono text-[11px] tracking-[0.15em] uppercase transition-colors
              border ${
                !running
                  ? 'border-j-border text-j-muted cursor-not-allowed'
                  : state !== 'idle'
                  ? 'border-j-border text-j-muted cursor-not-allowed'
                  : 'border-j-cyan text-j-cyan hover:bg-j-cyan/10 cursor-pointer'
              }`}
          >
            {triggering
              ? <Loader2 size={14} className="animate-spin" />
              : running
              ? <Mic size={14} strokeWidth={1.5} />
              : <MicOff size={14} strokeWidth={1.5} />
            }
            {triggering ? 'Activating...' : 'Hey Jarvis'}
          </button>

          {triggerMsg && (
            <p className="mt-2 text-center font-mono text-[10px] text-j-cyan tracking-[0.1em]">
              {triggerMsg}
            </p>
          )}
        </div>

        {/* Config details */}
        {status && (
          <div className="px-5 py-4 space-y-3">
            <span className="text-j-muted font-mono text-[10px] tracking-[0.15em] uppercase block">
              Configuration
            </span>
            {[
              ['STT Port', `:${status.stt_port}`],
              ['TTS Port', `:${status.tts_port}`],
              ['Wake Thresh', String(status.wake_sensitivity)],
              ['HA Control', status.ha_integration ? 'Enabled' : 'No token'],
              ['History', `${status.history_turns} turns`],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between">
                <span className="text-j-muted font-mono text-[10px] tracking-[0.1em]">{label}</span>
                <span className="text-j-text font-mono text-[10px]">{value}</span>
              </div>
            ))}
          </div>
        )}

        {/* Not running notice */}
        {!running && (
          <div className="mx-5 mb-4 p-3 border border-j-amber/40 rounded-sm bg-j-amber/5">
            <p className="text-j-amber font-mono text-[10px] leading-relaxed tracking-[0.05em]">
              Voice bridge offline.<br />
              Set <span className="text-j-text">WYOMING_ENABLED=true</span> and restart to activate.
            </p>
          </div>
        )}
      </div>

      {/* Right panel — conversation history */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-j-border bg-j-surf flex-shrink-0">
          <span className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase">
            Conversation History
          </span>
          {turns.length > 0 && (
            <button
              onClick={handleClear}
              className="flex items-center gap-1.5 text-j-muted hover:text-j-text
                         font-mono text-[10px] tracking-[0.1em] uppercase transition-colors"
            >
              <Trash2 size={11} strokeWidth={1.5} />
              Clear
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {error && (
            <div className="border border-j-red/40 bg-j-red/5 rounded-sm px-4 py-3">
              <p className="text-j-red font-mono text-[11px]">{error}</p>
            </div>
          )}

          {turns.length === 0 && !error && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Mic size={32} strokeWidth={1} className="text-j-border mb-4" />
              <p className="text-j-muted font-mono text-[11px] tracking-[0.1em] uppercase">
                No conversation yet
              </p>
              <p className="text-j-cdim font-mono text-[10px] mt-1">
                {running ? 'Say "Hey Jarvis" or press the button' : 'Enable voice bridge to start'}
              </p>
            </div>
          )}

          {turns.map((turn, i) => (
            <TurnCard key={i} turn={turn} index={i} />
          ))}
        </div>
      </div>
    </div>
  )
}
