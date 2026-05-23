import { useEffect, useRef, useState } from 'react'
import { ExternalLink, AlertTriangle, Loader } from 'lucide-react'
import type { HealthResponse } from '../api/client'

interface Props {
  health: HealthResponse | null
}

export default function HomeAssistant({ health }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(false)

  const haUrl = health?.services.ha_url ?? ''

  const embedUrl = haUrl

  useEffect(() => {
    setLoading(true)
    setError(false)
  }, [embedUrl])

  if (!haUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 p-10 text-center">
        <AlertTriangle size={40} className="text-j-amber" strokeWidth={1.5} />
        <div>
          <h2 className="text-j-amber font-bold text-[13px] tracking-[0.2em] uppercase mb-2 font-sans">
            HA URL Not Configured
          </h2>
          <p className="text-j-muted text-[11px] tracking-[0.05em] leading-relaxed font-sans max-w-[400px]">
            Set <span className="text-j-cyan font-mono">HA_URL</span> in the service environment
            to enable the Home Assistant embed.<br /><br />
            Example:<br />
            <span className="text-j-text font-mono">HA_URL=https://ha.example.com</span>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative flex flex-col w-full h-full">
      {/* Thin top bar showing the HA URL with an open-in-new-tab escape hatch */}
      <div className="flex items-center gap-3 px-4 py-1.5 border-b border-j-border bg-j-surf flex-shrink-0">
        <span className="text-j-cdim font-mono text-[10px] tracking-[0.1em] flex-1 truncate">
          {embedUrl}
        </span>
        <a
          href={haUrl}
          target="_blank"
          rel="noopener noreferrer"
          title="Open in new tab"
          className="text-j-muted hover:text-j-cyan transition-colors"
        >
          <ExternalLink size={13} strokeWidth={1.5} />
        </a>
      </div>

      {/* Loading / error overlay */}
      {(loading || error) && (
        <div className="absolute inset-0 top-[33px] flex flex-col items-center justify-center
                        bg-j-bg z-10 gap-4">
          {error ? (
            <>
              <AlertTriangle size={32} className="text-j-red" strokeWidth={1.5} />
              <p className="text-j-muted text-[11px] tracking-[0.1em] uppercase font-sans">
                Failed to load Home Assistant
              </p>
              <p className="text-j-cdim text-[10px] font-mono">
                Check HA_URL and that X-Frame-Options allows embedding
              </p>
            </>
          ) : (
            <>
              <Loader size={28} className="text-j-cyan animate-spin" strokeWidth={1.5} />
              <p className="text-j-muted text-[11px] tracking-[0.1em] uppercase font-sans">
                Connecting to Home Assistant…
              </p>
            </>
          )}
        </div>
      )}

      <iframe
        ref={iframeRef}
        src={embedUrl}
        title="Home Assistant"
        className="flex-1 w-full border-0"
        onLoad={() => { setLoading(false); setError(false) }}
        onError={() => { setLoading(false); setError(true) }}
        allow="fullscreen; microphone; camera"
        sandbox="allow-forms allow-modals allow-popups allow-same-origin allow-scripts allow-top-navigation-by-user-activation"
      />
    </div>
  )
}
