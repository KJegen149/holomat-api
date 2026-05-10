import { useEffect, useRef } from 'react'
import type { LogEntry } from '../hooks/useWebSocket'

const LVL_COLOR: Record<string, string> = {
  INFO:    'text-j-green',
  WARNING: 'text-j-amber',
  ERROR:   'text-j-red',
  DEBUG:   'text-j-muted',
}

const MSG_COLOR: Record<string, string> = {
  INFO:    'text-j-green',
  WARNING: 'text-j-amber',
  ERROR:   'text-j-red',
  DEBUG:   'text-j-muted',
}

interface Props {
  logs: LogEntry[]
}

export default function Console({ logs }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <aside className="w-[300px] border-l border-j-border bg-j-surf flex flex-col flex-shrink-0 overflow-hidden">
      <div className="flex items-baseline justify-between px-4 py-2.5 border-b border-j-border flex-shrink-0">
        <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
          SYSTEM // <span className="text-j-muted font-normal">RT-LOG</span>
        </span>
        <span className="text-[10px] tracking-[0.1em] text-j-muted uppercase font-sans">ROOT@JARVIS</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-2.5 font-mono text-[11px] leading-[1.7]">
        {logs.map((log) => {
          const lvl = (log.level ?? 'INFO').toUpperCase()
          return (
            <div key={log.id} className="whitespace-pre-wrap break-all">
              <span className="text-j-cdim">[{log.ts}]</span>{' '}
              <span className={LVL_COLOR[lvl] ?? 'text-j-green'}>{lvl.padEnd(8)}</span>{' '}
              <span className={MSG_COLOR[lvl] ?? 'text-j-green'}>{log.message}</span>
            </div>
          )
        })}
        <div ref={bottomRef} />
        <span className="inline-block w-[7px] h-[13px] bg-j-green align-middle animate-cur-blink" />
      </div>
    </aside>
  )
}
