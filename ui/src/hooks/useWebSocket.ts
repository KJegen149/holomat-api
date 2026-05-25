import { useEffect, useRef, useState } from 'react'
import { triggerAuthExpired } from '../api/client'

// Custom close code from the backend (api/websocket.py) — "your session
// lapsed, drop back to login". We do NOT reconnect on this code.
const WS_AUTH_FAILED = 4401

export interface LogEntry {
  id: number
  ts: string
  level: string
  message: string
}

let _logId = 0

export function useWebSocket() {
  const [logs, setLogs] = useState<LogEntry[]>([{
    id: ++_logId,
    ts: '--:--:--',
    level: 'INFO',
    message: 'Holomat initializing...',
  }])
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws`)
      wsRef.current = ws

      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping')
      }, 20000)

      ws.onopen = () => {
        setLogs(prev => [...prev, {
          id: ++_logId,
          ts: new Date().toTimeString().slice(0, 8),
          level: 'INFO',
          message: 'WebSocket connected',
        }])
      }

      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data as string) as { type?: string; ts?: string; level?: string; message?: string }
          if (d.type === 'log') {
            const ts = d.ts ? new Date(d.ts).toTimeString().slice(0, 8) : '--:--:--'
            setLogs(prev => {
              const next = [...prev, { id: ++_logId, ts, level: d.level ?? 'INFO', message: d.message ?? '' }]
              return next.length > 300 ? next.slice(next.length - 300) : next
            })
          }
        } catch { /* non-JSON frames ignored */ }
      }

      ws.onclose = (e) => {
        clearInterval(pingInterval)
        if (e.code === WS_AUTH_FAILED) {
          // Server rejected the cookie — drop to login, don't reconnect.
          triggerAuthExpired()
          return
        }
        reconnectTimer = setTimeout(connect, 3000)
      }

      return () => clearInterval(pingInterval)
    }

    const cleanup = connect()

    return () => {
      clearTimeout(reconnectTimer)
      cleanup?.()
      wsRef.current?.close()
    }
  }, [])

  return logs
}
