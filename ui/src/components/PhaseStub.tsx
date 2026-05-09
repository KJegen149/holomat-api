import type { LucideIcon } from 'lucide-react'

interface Props {
  phase: string
  title: string
  description: string
  icon: LucideIcon
  capabilities?: string[]
}

export default function PhaseStub({ phase, title, description, icon: Icon, capabilities = [] }: Props) {
  return (
    <div className="flex items-center justify-center h-full p-8 overflow-y-auto">
      <div className="max-w-md w-full border border-j-border bg-j-surf rounded-sm p-8 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 border border-j-cdim rounded-sm mb-6">
          <span className="text-j-cdim font-mono text-[10px] tracking-[0.2em] uppercase">PHASE {phase}</span>
        </div>

        <div className="flex items-center justify-center w-16 h-16 mx-auto mb-6 border border-j-border rounded-full">
          <Icon size={28} strokeWidth={1} className="text-j-cyan" />
        </div>

        <h1 className="text-j-cyan font-bold text-xl tracking-[0.15em] uppercase mb-3 font-sans">
          {title}
        </h1>

        <p className="text-j-muted text-[13px] tracking-[0.03em] leading-relaxed mb-6 font-sans">
          {description}
        </p>

        {capabilities.length > 0 && (
          <div className="text-left border-t border-j-border pt-5">
            <h3 className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase mb-3">
              Planned Capabilities
            </h3>
            <ul className="space-y-2">
              {capabilities.map((cap, i) => (
                <li key={i} className="flex items-start gap-2 font-mono text-[11px] text-j-muted">
                  <span className="text-j-cdim mt-0.5 flex-shrink-0">·</span>
                  {cap}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-j-border">
          <span className="text-j-muted font-mono text-[10px] tracking-[0.15em] uppercase">
            COMING SOON — PHASE {phase}
          </span>
        </div>
      </div>
    </div>
  )
}
