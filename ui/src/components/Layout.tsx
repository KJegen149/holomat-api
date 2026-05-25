import { useEffect, useState, type ReactNode } from 'react'
import { Keyboard, LogOut } from 'lucide-react'
import Console from './Console'
import OnScreenKeyboard from './OnScreenKeyboard'
import SummonNav from './SummonNav'
import type { LogEntry } from '../hooks/useWebSocket'
import type { HealthResponse } from '../api/client'

interface Props {
  children: ReactNode
  logs: LogEntry[]
  health: HealthResponse | null
  healthError: string | null
  username?: string | null
  onLogout?: () => Promise<void> | void
}

export default function Layout({ children, logs, health, healthError, username, onLogout }: Props) {
  const [time, setTime] = useState(() => new Date().toTimeString().slice(0, 8))
  const [showKeyboard, setShowKeyboard] = useState(false)

  useEffect(() => {
    const id = setInterval(() => setTime(new Date().toTimeString().slice(0, 8)), 1000)
    return () => clearInterval(id)
  }, [])

  const sysClass = healthError ? 'err' : health ? '' : 'idle'
  const calClass = !health ? 'idle' : health.calibration.valid ? '' : 'warn'
  const sysLabel = healthError ? 'OFFLINE' : health ? 'OPTIMAL' : 'INITIALIZING'
  const calLabel = !health ? 'CALIBRATION' : health.calibration.valid ? 'CALIBRATED' : 'CALIB REQUIRED'

  return (
    <div className="flex flex-col w-full h-full">
      {/* Top bar */}
      <header
        className="flex items-center gap-5 px-6 h-14 flex-shrink-0 z-20
                   backdrop-blur-j border-b border-j-border/15"
        style={{ background: 'linear-gradient(180deg, rgba(5,6,9,0.92), rgba(5,6,9,0.55))' }}
      >
        <div>
          <div className="j-brand-wordmark text-lg uppercase">JARVIS</div>
          <div className="text-j-muted-dim text-[9px] tracking-[0.18em] uppercase">
            Joint Automation, Robotics &amp; Vision Intelligence System
          </div>
        </div>
        <div className="flex-1" />
        <div className={`j-status-pill ${sysClass}`}>
          <span className="dot" />{sysLabel}
        </div>
        <div className={`j-status-pill ${calClass}`}>
          <span className="dot" />{calLabel}
        </div>
        <button
          type="button"
          title="On-screen keyboard"
          onClick={() => setShowKeyboard(s => !s)}
          className={`p-2 rounded-j-sm border transition-colors duration-200 ${
            showKeyboard
              ? 'border-j-cyan text-j-cyan bg-j-cyan/10 shadow-j-glow'
              : 'border-j-border/20 text-j-muted hover:text-j-text hover:border-j-text/40'
          }`}
        >
          <Keyboard size={15} strokeWidth={1.5} />
        </button>
        {onLogout && (
          <button
            type="button"
            title={username ? `Sign out (${username})` : 'Sign out'}
            onClick={() => { void onLogout() }}
            className="p-2 rounded-j-sm border border-j-border/20 text-j-muted
                       hover:text-j-red hover:border-j-red/55 transition-colors duration-200"
          >
            <LogOut size={15} strokeWidth={1.5} />
          </button>
        )}
        <div className="font-mono text-base font-medium tracking-[0.12em] text-j-text">{time}</div>
      </header>

      {/* Content row — orbital summon nav is page-overlay (SummonNav); Console
          is a slide-out from the right edge, positioned absolutely against
          this row. */}
      <div className="relative flex flex-1 overflow-hidden">
        <main className="flex-1 overflow-hidden relative">
          {children}
        </main>
        <Console logs={logs} />
      </div>

      <SummonNav />

      {showKeyboard && <OnScreenKeyboard onClose={() => setShowKeyboard(false)} />}

      {/* Bottom bar */}
      <footer
        className="flex items-center gap-4 px-6 py-2 flex-shrink-0 z-10
                   font-mono text-[10px] text-j-muted-dim tracking-[0.1em]
                   border-t border-j-border/15 backdrop-blur-j"
        style={{ background: 'linear-gradient(0deg, rgba(5,6,9,0.85), rgba(5,6,9,0.4))' }}
      >
        <span>{health?.version ? `HOLOMAT v${health.version}` : 'HOLOMAT'}</span>
        {username && <span>USER {username.toUpperCase()}</span>}
        <div className="flex-1" />
        <span>{`http://${window.location.host}`}</span>
      </footer>
    </div>
  )
}
