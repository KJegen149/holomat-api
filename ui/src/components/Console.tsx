import { useEffect, useRef, useState } from 'react'
import { Terminal } from 'lucide-react'
import type { LogEntry } from '../hooks/useWebSocket'

const LVL_COLOR: Record<string, string> = {
  INFO:    'text-j-green',
  WARNING: 'text-j-amber',
  ERROR:   'text-j-red',
  DEBUG:   'text-j-muted',
}

interface Props {
  logs: LogEntry[]
}

const PANEL_WIDTH = 320
const HANDLE_WIDTH = 8

/* Slide-out RT-log console. Collapsed by default: only a luminous strip on
   the right edge. Hover the strip (or the 28px hot zone next to it) to
   expand; the panel auto-collapses ~280ms after the pointer leaves. The
   strip glows amber/red briefly when a WARNING / ERROR is appended so you
   notice activity even when collapsed. */
export default function Console({ logs }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [accent, setAccent] = useState<'cyan' | 'amber' | 'red'>('cyan')
  const bottomRef = useRef<HTMLDivElement>(null)
  const closeTimer = useRef<number | null>(null)
  const accentTimer = useRef<number | null>(null)
  const lastSeenId = useRef<number>(0)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    // Strip glow on new WARN/ERROR while collapsed.
    const fresh = logs.filter(l => l.id > lastSeenId.current)
    if (fresh.length === 0) return
    lastSeenId.current = logs[logs.length - 1].id
    const worst = fresh.reduce<'cyan' | 'amber' | 'red'>((acc, l) => {
      const lvl = (l.level ?? '').toUpperCase()
      if (lvl === 'ERROR') return 'red'
      if (lvl === 'WARNING' && acc !== 'red') return 'amber'
      return acc
    }, 'cyan')
    if (worst !== 'cyan' && !expanded) {
      setAccent(worst)
      if (accentTimer.current != null) window.clearTimeout(accentTimer.current)
      accentTimer.current = window.setTimeout(() => setAccent('cyan'), 2200)
    }
  }, [logs, expanded])

  useEffect(() => () => {
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current)
    if (accentTimer.current != null) window.clearTimeout(accentTimer.current)
  }, [])

  const open = () => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
    setExpanded(true)
  }
  const scheduleClose = () => {
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(() => setExpanded(false), 280)
  }

  // Hot zone hover on the right ~28px
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      if (window.innerWidth - e.clientX < 28 && e.clientY > 56 && e.clientY < window.innerHeight - 40) {
        open()
      }
    }
    window.addEventListener('pointermove', onMove)
    return () => window.removeEventListener('pointermove', onMove)
  }, [])

  const stripColor = {
    cyan:  'rgba(0, 220, 255, 0.55)',
    amber: 'rgba(255, 180, 60, 0.75)',
    red:   'rgba(255, 80, 100, 0.85)',
  }[accent]
  const stripGlow = {
    cyan:  '0 0 14px rgba(0, 220, 255, 0.35)',
    amber: '0 0 18px rgba(255, 180, 60, 0.55)',
    red:   '0 0 22px rgba(255, 80, 100, 0.7)',
  }[accent]

  return (
    <aside
      className="absolute inset-y-0 right-0 z-30 flex"
      style={{
        width: PANEL_WIDTH + HANDLE_WIDTH,
        transform: expanded ? 'translateX(0)' : `translateX(${PANEL_WIDTH}px)`,
        transition: 'transform 280ms cubic-bezier(.2,.7,.2,1)',
        pointerEvents: 'none',
      }}
      onPointerEnter={open}
      onPointerLeave={scheduleClose}
    >
      {/* Luminous strip handle (always visible) */}
      <button
        type="button"
        onClick={() => setExpanded(e => !e)}
        aria-label={expanded ? 'Collapse log console' : 'Expand log console'}
        className="relative flex-shrink-0 cursor-pointer"
        style={{
          width: HANDLE_WIDTH,
          pointerEvents: 'auto',
          background: `linear-gradient(180deg,
            transparent 0%,
            ${stripColor.replace('0.55', '0.18').replace('0.75', '0.30').replace('0.85', '0.35')} 12%,
            ${stripColor} 50%,
            rgba(140, 110, 255, 0.32) 75%,
            transparent 100%)`,
          boxShadow: stripGlow,
          border: 0,
          transition: 'background 400ms ease, box-shadow 400ms ease',
        }}
      >
        <span
          aria-hidden
          className="absolute top-1/2 -translate-y-1/2 rounded"
          style={{
            left: -4, width: 4, height: 64,
            background: stripColor,
            boxShadow: stripGlow,
            opacity: 0.7,
            transition: 'background 400ms ease, box-shadow 400ms ease',
          }}
        />
      </button>

      {/* Panel body */}
      <div
        className="j-panel rounded-l-j-lg rounded-r-none border-r-0 flex flex-col flex-shrink-0"
        style={{ width: PANEL_WIDTH, pointerEvents: 'auto' }}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-j-border/15 flex-shrink-0">
          <span className="text-[11px] font-medium tracking-[0.2em] text-j-cyan uppercase flex items-center gap-2">
            <Terminal size={12} strokeWidth={1.5} />
            System <span className="text-j-muted">// RT-Log</span>
          </span>
          <span className="text-[10px] tracking-[0.1em] text-j-muted-dim uppercase">root@jarvis</span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-2.5 font-mono text-[11px] leading-[1.7]">
          {logs.map(log => {
            const lvl = (log.level ?? 'INFO').toUpperCase()
            const cls = LVL_COLOR[lvl] ?? 'text-j-green'
            return (
              <div key={log.id} className="whitespace-pre-wrap break-all">
                <span className="text-j-cdim">[{log.ts}]</span>{' '}
                <span className={cls}>{lvl.padEnd(8)}</span>{' '}
                <span className={cls}>{log.message}</span>
              </div>
            )
          })}
          <div ref={bottomRef} />
          <span className="inline-block w-[7px] h-[13px] bg-j-green align-middle animate-cur-blink" />
        </div>
      </div>
    </aside>
  )
}
