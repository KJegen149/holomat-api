export type PillState = 'ok' | 'warn' | 'err' | 'idle'

const DOT: Record<PillState, string> = {
  ok:   'bg-j-green animate-pulse-green',
  warn: 'bg-j-amber',
  err:  'bg-j-red',
  idle: 'bg-j-cdim',
}

const LABEL: Record<PillState, string> = {
  ok:   'text-j-text',
  warn: 'text-j-amber',
  err:  'text-j-red',
  idle: 'text-j-muted',
}

interface Props {
  state: PillState
  label: string
}

export default function StatusPill({ state, label }: Props) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-[7px] h-[7px] rounded-full flex-shrink-0 ${DOT[state]}`} />
      <span className={`text-[11px] tracking-[0.1em] uppercase font-sans ${LABEL[state]}`}>
        {label}
      </span>
    </div>
  )
}
