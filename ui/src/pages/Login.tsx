import { useEffect, useRef, useState } from 'react'
import { Lock, Loader2, ShieldCheck } from 'lucide-react'
import RadarAnimation from '../components/RadarAnimation'
import OnScreenKeyboard from '../components/OnScreenKeyboard'
import { fetchHealth, type HealthResponse } from '../api/client'

interface Props {
  onLogin: (username: string, password: string) => Promise<void>
}

export default function Login({ onLogin }: Props) {
  const [username, setUsername] = useState('holomat')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showKeyboard, setShowKeyboard] = useState(true)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthErr, setHealthErr] = useState(false)
  const userRef = useRef<HTMLInputElement>(null)
  const passRef = useRef<HTMLInputElement>(null)

  // Status pill: poll /api/health so the login screen still feels alive.
  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const h = await fetchHealth()
        if (alive) { setHealth(h); setHealthErr(false) }
      } catch {
        if (alive) { setHealth(null); setHealthErr(true) }
      }
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  // Auto-focus the empty field. Username is prefilled to the default; if the
  // operator changed it, password is the natural starting point.
  useEffect(() => {
    if (!username) userRef.current?.focus()
    else passRef.current?.focus()
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password || busy) return
    setBusy(true)
    setError(null)
    try {
      await onLogin(username, password)
      // success: useAuth flips status to 'authed' and App rerenders → no nav needed
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Login failed')
      setBusy(false)
      passRef.current?.focus()
      passRef.current?.select()
    }
  }

  const sysLabel = healthErr ? 'OFFLINE' : health ? 'OPTIMAL' : 'INITIALIZING'
  const sysColor = healthErr ? 'text-j-red' : health ? 'text-j-green' : 'text-j-amber'

  return (
    <div className="flex flex-col w-full h-full bg-j-bg">
      {/* Top bar — mirrors Layout's, minus the nav */}
      <header className="flex items-center gap-6 px-6 py-2.5 border-b border-j-border bg-j-surf flex-shrink-0">
        <div>
          <div className="text-j-cyan font-bold text-lg tracking-[0.2em] uppercase font-sans">JARVIS</div>
          <div className="text-j-muted text-[10px] tracking-[0.15em] uppercase font-sans">
            Joint Automation, Robotics &amp; Vision Intelligence System
          </div>
        </div>
        <div className="flex-1" />
        <div className={`flex items-center gap-2 font-mono text-[10px] tracking-[0.15em] ${sysColor}`}>
          <span className="w-1.5 h-1.5 rounded-full bg-current" />
          SYSTEM {sysLabel}
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 flex items-center justify-center p-10">
          <div className="flex items-center gap-16">
            <RadarAnimation label="ACCESS" sublabel="LOCKED" />

            <form
              onSubmit={handleSubmit}
              className="w-[340px] border border-j-border rounded-sm bg-j-surf overflow-hidden"
            >
              <div className="px-5 py-3 border-b border-j-border flex items-center gap-2">
                <Lock size={13} className="text-j-cyan" strokeWidth={1.5} />
                <span className="font-mono text-[11px] text-j-cyan tracking-[0.2em] uppercase">
                  Authentication
                </span>
              </div>

              <div className="px-5 py-5 space-y-4">
                <div className="space-y-1.5">
                  <label className="block font-mono text-[10px] text-j-muted tracking-[0.1em] uppercase">
                    Username
                  </label>
                  <input
                    ref={userRef}
                    type="text"
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    autoComplete="username"
                    spellCheck={false}
                    autoCapitalize="off"
                    className="w-full bg-j-bg border border-j-border rounded-sm px-3 py-2
                               font-mono text-[12px] text-j-text placeholder-j-cdim
                               focus:outline-none focus:border-j-cyan transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="block font-mono text-[10px] text-j-muted tracking-[0.1em] uppercase">
                    Password
                  </label>
                  <input
                    ref={passRef}
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    autoComplete="current-password"
                    className="w-full bg-j-bg border border-j-border rounded-sm px-3 py-2
                               font-mono text-[12px] text-j-text placeholder-j-cdim
                               focus:outline-none focus:border-j-cyan transition-colors"
                  />
                </div>

                {error && (
                  <div className="border border-j-red/40 bg-j-red/5 rounded-sm px-3 py-2">
                    <p className="font-mono text-[10px] text-j-red leading-relaxed">
                      ✗ {error}
                    </p>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={!username || !password || busy}
                  className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-sm border
                              font-mono text-[11px] tracking-[0.2em] uppercase transition-colors
                              ${busy || !username || !password
                                ? 'border-j-border text-j-muted cursor-not-allowed'
                                : 'border-j-cyan text-j-cyan hover:bg-j-cyan/10 cursor-pointer'
                              }`}
                >
                  {busy ? <Loader2 size={12} className="animate-spin" /> : <ShieldCheck size={12} />}
                  {busy ? 'Engaging…' : 'Engage'}
                </button>

                <button
                  type="button"
                  onClick={() => setShowKeyboard(s => !s)}
                  className="w-full font-mono text-[9px] text-j-cdim tracking-[0.15em] uppercase
                             hover:text-j-text transition-colors"
                >
                  {showKeyboard ? 'Hide on-screen keyboard' : 'Show on-screen keyboard'}
                </button>
              </div>
            </form>
          </div>
        </main>
      </div>

      {showKeyboard && <OnScreenKeyboard onClose={() => setShowKeyboard(false)} />}

      <footer className="flex items-center gap-4 px-6 py-2 border-t border-j-border bg-j-surf flex-shrink-0
                         font-mono text-[10px] text-j-muted tracking-[0.1em]">
        <span className="text-j-cdim">{health?.version ? `HOLOMAT v${health.version}` : 'HOLOMAT'}</span>
        <div className="flex-1" />
        <span className="text-j-cdim">{`http://${window.location.host}`}</span>
      </footer>
    </div>
  )
}
