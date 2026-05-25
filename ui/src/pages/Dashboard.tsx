import { useEffect, useState } from 'react'
import { Boxes, Crosshair, Printer, Activity, AlertTriangle, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import ParticleSphere, { type ParticleMode } from '../components/ParticleSphere'
import { useVoiceState } from '../hooks/useVoiceState'
import { fetchPrintQueue, type HealthResponse, type PrintJob } from '../api/client'

interface Props {
  health: HealthResponse | null
  healthError: string | null
}

interface HudCardProps {
  label: string
  value: string
  sub?: string
  icon: LucideIcon
  position: 'tl' | 'tr' | 'bl' | 'br'
  tone?: 'normal' | 'warn'
}

const POSITION_CLASS: Record<HudCardProps['position'], string> = {
  tl: 'top-6 left-6',
  tr: 'top-6 right-6',
  bl: 'bottom-6 left-6',
  br: 'bottom-6 right-6',
}

function HudCard({ label, value, sub, icon: Icon, position, tone = 'normal' }: HudCardProps) {
  const border = tone === 'warn' ? 'border-j-amber/40' : 'border-j-border/20'
  return (
    <div
      className={`absolute ${POSITION_CLASS[position]} j-panel ${border}
                  px-5 py-4 min-w-[180px] pointer-events-auto`}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Icon size={11} strokeWidth={1.5} className={tone === 'warn' ? 'text-j-amber' : 'text-j-cyan'} />
        <span className="text-[9px] uppercase tracking-[0.22em] text-j-muted font-medium">{label}</span>
      </div>
      <div className={`text-2xl font-light leading-tight ${tone === 'warn' ? 'text-j-amber' : 'text-j-text'}`}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-j-muted mt-0.5">{sub}</div>}
    </div>
  )
}

function activePrintSummary(jobs: PrintJob[]): { value: string; sub: string } {
  if (jobs.length === 0) return { value: 'Idle', sub: 'No active prints' }
  const j = jobs[0]
  const pct = Math.round(j.progress * 100)
  const stateLabel = j.state === 'printing' ? `${pct}%` :
    j.state.charAt(0).toUpperCase() + j.state.slice(1)
  const rest = jobs.length > 1 ? ` · ${jobs.length - 1} queued` : ''
  return { value: stateLabel, sub: `${j.name}${rest}` }
}

/* Voice bridge has four states; the sphere only differentiates three.
   'thinking' (LLM working) collapses to 'listening' visually — same
   suspenseful pulse, no ripples yet. */
function voiceToSphere(v: ReturnType<typeof useVoiceState>): ParticleMode {
  if (v === 'speaking') return 'speaking'
  if (v === 'listening' || v === 'thinking') return 'listening'
  return 'idle'
}

export default function Dashboard({ health, healthError }: Props) {
  const [queue, setQueue] = useState<{ active: PrintJob[]; history: PrintJob[] } | null>(null)
  const [greeting, setGreeting] = useState('Standing by.')
  const voice = useVoiceState()
  const sphereMode = voiceToSphere(voice)

  useEffect(() => {
    const tick = () => fetchPrintQueue().then(setQueue).catch(() => { /* keep stale */ })
    tick()
    const id = setInterval(tick, 5_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const hour = new Date().getHours()
    const period =
      hour < 5  ? 'Burning the midnight oil' :
      hour < 12 ? 'Good morning'   :
      hour < 17 ? 'Good afternoon' :
      hour < 22 ? 'Good evening'   : 'Burning the midnight oil'
    setGreeting(`${period}. Standing by.`)
  }, [])

  const calibValid = health?.calibration.valid ?? false
  const calibValue = !health ? '—' : calibValid ? 'Locked' : 'Required'
  const calibSub   = !health
    ? 'Awaiting handshake'
    : calibValid
      ? `${health.calibration.point_count} points · RMSE ${health.calibration.rmse?.toFixed(2) ?? '—'}`
      : 'Place ChArUco board and run wizard'

  const libCount = health?.scanner.library_count ?? 0
  const libSub   = libCount === 0 ? 'Scan an object to begin' : `${libCount} object${libCount === 1 ? '' : 's'} catalogued`

  const printSummary = activePrintSummary(queue?.active ?? [])

  const services = health?.services
  const sysValue = healthError ? 'Offline' : !health ? 'Booting' : 'Optimal'
  const sysSub   = healthError
    ? 'Cannot reach API'
    : services
      ? `HA ${services.ha_bridge ? '✓' : '×'} · SMB ${services.smb_watcher ? '✓' : '×'} · WS ${services.ws_clients}`
      : 'Reading telemetry'

  return (
    <div className="relative w-full h-full overflow-hidden">
      <ParticleSphere mode={sphereMode} />

      {/* Greeting & status, anchored low-center over the sphere */}
      <div className="absolute left-1/2 bottom-[18%] -translate-x-1/2 text-center pointer-events-none px-6 max-w-[560px]">
        <div className="text-[10px] uppercase tracking-[0.3em] text-j-muted mb-2">
          JARVIS · {voice === 'idle' ? 'Ready' :
                    voice === 'listening' ? 'Listening' :
                    voice === 'thinking' ? 'Thinking' :
                    'Speaking'}
        </div>
        <div className="text-xl font-light leading-relaxed text-j-text">
          {greeting}
        </div>
        {health && !calibValid && (
          <Link
            to="/settings"
            className="pointer-events-auto inline-flex items-center gap-2 mt-4 px-4 py-2 rounded-full
                       border border-j-amber/40 text-j-amber text-xs uppercase tracking-[0.18em]
                       hover:bg-j-amber/10 transition-colors"
          >
            <AlertTriangle size={12} /> Calibration required
          </Link>
        )}
      </div>

      {/* HUD cards */}
      <HudCard
        label="System"
        value={sysValue}
        sub={sysSub}
        icon={Activity}
        position="tl"
        tone={healthError ? 'warn' : 'normal'}
      />
      <HudCard
        label="Calibration"
        value={calibValue}
        sub={calibSub}
        icon={Crosshair}
        position="tr"
        tone={!calibValid && health ? 'warn' : 'normal'}
      />
      <HudCard
        label="Library"
        value={String(libCount)}
        sub={libSub}
        icon={Boxes}
        position="bl"
      />
      <HudCard
        label="Print Queue"
        value={printSummary.value}
        sub={printSummary.sub}
        icon={Printer}
        position="br"
      />
    </div>
  )
}
