import { useEffect, useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Crosshair, Scan, Printer, Image, Settings, Home } from 'lucide-react'
import Console from './Console'
import StatusPill, { type PillState } from './StatusPill'
import type { LogEntry } from '../hooks/useWebSocket'
import type { HealthResponse } from '../api/client'

interface NavItem {
  path: string
  icon: typeof LayoutDashboard
  label: string
  end: boolean
  phase?: string
}

const NAV: NavItem[] = [
  { path: '/',                icon: LayoutDashboard, label: 'DASHBOARD',      end: true  },
  { path: '/calibration',     icon: Crosshair,       label: 'CALIBRATION',    end: false },
  { path: '/home-assistant',  icon: Home,            label: 'HOME ASSISTANT', end: false },
  { path: '/scanner',         icon: Scan,            label: 'SCANNER',        end: false, phase: '4' },
  { path: '/print',           icon: Printer,         label: 'PRINT',          end: false, phase: '7' },
  { path: '/gallery',         icon: Image,           label: 'GALLERY',        end: false, phase: '6' },
  { path: '/settings',        icon: Settings,        label: 'SETTINGS',       end: false, phase: '9' },
]

interface Props {
  children: ReactNode
  logs: LogEntry[]
  health: HealthResponse | null
  healthError: string | null
}

export default function Layout({ children, logs, health, healthError }: Props) {
  const [time, setTime] = useState(() => new Date().toTimeString().slice(0, 8))

  useEffect(() => {
    const id = setInterval(() => setTime(new Date().toTimeString().slice(0, 8)), 1000)
    return () => clearInterval(id)
  }, [])

  const sysState: PillState = healthError ? 'err' : health ? 'ok' : 'idle'
  const calState: PillState = !health ? 'idle' : health.calibration.valid ? 'ok' : 'warn'
  const sysLabel  = healthError ? 'OFFLINE' : health ? 'OPTIMAL' : 'INITIALIZING'
  const calLabel  = !health ? 'CALIBRATION' : health.calibration.valid ? 'CALIBRATED' : 'CALIB REQUIRED'

  return (
    <div className="flex flex-col w-full h-full bg-j-bg">
      {/* Top bar */}
      <header className="flex items-center gap-6 px-6 py-2.5 border-b border-j-border bg-j-surf flex-shrink-0">
        <div>
          <div className="text-j-cyan font-bold text-lg tracking-[0.2em] uppercase font-sans">JARVIS</div>
          <div className="text-j-muted text-[10px] tracking-[0.15em] uppercase font-sans">
            Joint Automation, Robotics &amp; Vision Intelligence System
          </div>
        </div>
        <div className="flex-1" />
        <StatusPill state={sysState} label={sysLabel} />
        <StatusPill state={calState} label={calLabel} />
        <div className="text-j-text font-mono text-base font-semibold tracking-[0.1em]">{time}</div>
      </header>

      {/* Content row */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <nav className="flex flex-col w-14 border-r border-j-border bg-j-surf flex-shrink-0 py-3 gap-1">
          {NAV.map(({ path, icon: Icon, label, end, phase }) => (
            <NavLink
              key={path}
              to={path}
              end={end}
              title={label}
              className={({ isActive }) =>
                `relative group flex items-center justify-center h-10 w-10 mx-auto rounded-sm
                 transition-colors duration-150 cursor-pointer
                 ${isActive ? 'text-j-cyan bg-j-border' : 'text-j-muted hover:text-j-text hover:bg-j-border/50'}`
              }
            >
              <Icon size={18} strokeWidth={1.5} />
              {/* Tooltip */}
              <span className="absolute left-full ml-2 px-2 py-1 bg-j-surf border border-j-border
                               text-j-text text-[10px] tracking-[0.15em] uppercase whitespace-nowrap
                               opacity-0 group-hover:opacity-100 pointer-events-none z-50 rounded-sm
                               transition-opacity duration-150 font-sans">
                {label}
                {phase ? <span className="ml-1.5 text-j-cdim">P{phase}</span> : null}
              </span>
            </NavLink>
          ))}
        </nav>

        {/* Page content */}
        <main className="flex-1 overflow-hidden">
          {children}
        </main>

        {/* Live log console */}
        <Console logs={logs} />
      </div>

      {/* Bottom bar */}
      <footer className="flex items-center gap-4 px-6 py-2 border-t border-j-border bg-j-surf flex-shrink-0
                         font-mono text-[10px] text-j-muted tracking-[0.1em]">
        <span className="text-j-cdim">HOLOMAT v0.7.0 // PHASE 7 — PRINT QUEUE</span>
        <div className="flex-1" />
        <span className="text-j-cdim">{`http://${window.location.host}`}</span>
      </footer>
    </div>
  )
}
