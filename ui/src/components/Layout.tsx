import { useEffect, useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Crosshair, Scan, Printer, Image, Settings, Home, Mic, Keyboard, Boxes, LogOut } from 'lucide-react'
import Console from './Console'
import StatusPill, { type PillState } from './StatusPill'
import OnScreenKeyboard from './OnScreenKeyboard'
import type { LogEntry } from '../hooks/useWebSocket'
import type { HealthResponse } from '../api/client'

interface NavItem {
  path: string
  icon: typeof LayoutDashboard
  label: string
  end: boolean
}

const NAV: NavItem[] = [
  { path: '/',                icon: LayoutDashboard, label: 'DASHBOARD',      end: true  },
  { path: '/calibration',     icon: Crosshair,       label: 'CALIBRATION',    end: false },
  { path: '/home-assistant',  icon: Home,            label: 'HOME ASSISTANT', end: false },
  { path: '/scanner',         icon: Scan,            label: 'SCANNER',        end: false },
  { path: '/print',           icon: Printer,         label: 'PRINT',          end: false },
  { path: '/models',          icon: Boxes,           label: 'MODELS',         end: false },
  { path: '/gallery',         icon: Image,           label: 'GALLERY',        end: false },
  { path: '/voice',           icon: Mic,             label: 'VOICE',          end: false },
  { path: '/settings',        icon: Settings,        label: 'SETTINGS',       end: false },
]

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
        <button
          type="button"
          title="On-screen keyboard"
          onClick={() => setShowKeyboard(s => !s)}
          className={`p-1.5 rounded-sm border transition-colors ${
            showKeyboard
              ? 'border-j-cyan text-j-cyan bg-j-cyan/10'
              : 'border-j-border text-j-muted hover:text-j-text hover:border-j-text'
          }`}
        >
          <Keyboard size={15} strokeWidth={1.5} />
        </button>
        {onLogout && (
          <button
            type="button"
            title={username ? `Sign out (${username})` : 'Sign out'}
            onClick={() => { void onLogout() }}
            className="p-1.5 rounded-sm border border-j-border text-j-muted
                       hover:text-j-red hover:border-j-red transition-colors"
          >
            <LogOut size={15} strokeWidth={1.5} />
          </button>
        )}
        <div className="text-j-text font-mono text-base font-semibold tracking-[0.1em]">{time}</div>
      </header>

      {/* Content row */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <nav className="flex flex-col w-14 border-r border-j-border bg-j-surf flex-shrink-0 py-3 gap-1">
          {NAV.map(({ path, icon: Icon, label, end }) => (
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

      {showKeyboard && <OnScreenKeyboard onClose={() => setShowKeyboard(false)} />}

      {/* Bottom bar */}
      <footer className="flex items-center gap-4 px-6 py-2 border-t border-j-border bg-j-surf flex-shrink-0
                         font-mono text-[10px] text-j-muted tracking-[0.1em]">
        <span className="text-j-cdim">{health?.version ? `HOLOMAT v${health.version}` : 'HOLOMAT'}</span>
        {username && <span className="text-j-cdim">USER {username.toUpperCase()}</span>}
        <div className="flex-1" />
        <span className="text-j-cdim">{`http://${window.location.host}`}</span>
      </footer>
    </div>
  )
}
