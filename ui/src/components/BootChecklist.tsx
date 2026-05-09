import type { HealthResponse } from '../api/client'

type S = 'ok' | 'warn' | 'err' | 'pending'

const ICON: Record<S, string> = { ok: '✓', warn: '⚠', err: '✗', pending: '·' }
const COLOR: Record<S, string> = {
  ok:      'text-j-green',
  warn:    'text-j-amber',
  err:     'text-j-red',
  pending: 'text-j-muted',
}

interface Check { id: string; state: S; detail: string }

function build(health: HealthResponse | null, error: string | null): Check[] {
  if (error) return [
    { id: 'api',   state: 'err',     detail: `API SERVER — UNREACHABLE (${error})` },
    { id: 'cal',   state: 'pending', detail: 'CALIBRATION DATA' },
    { id: 'cam',   state: 'pending', detail: 'CAMERA DEVICE' },
    { id: 'prt',   state: 'pending', detail: 'PRINTER CONFIG' },
    { id: 'orc',   state: 'pending', detail: 'ORCA SLICER' },
    { id: 'osc',   state: 'pending', detail: 'OPENSCAD' },
    { id: 'cf',    state: 'pending', detail: 'CLOUDFLARE API' },
  ]

  if (!health) return [
    'API SERVER', 'CALIBRATION DATA', 'CAMERA DEVICE',
    'PRINTER CONFIG', 'ORCA SLICER', 'OPENSCAD', 'CLOUDFLARE API',
  ].map((d, i) => ({ id: String(i), state: 'pending' as S, detail: d }))

  const { calibration: c, hardware: hw, services: sv } = health
  return [
    { id: 'api', state: 'ok',
      detail: 'API SERVER — ONLINE' },
    { id: 'cal', state: c.valid ? 'ok' : 'warn',
      detail: c.valid
        ? `CALIBRATION — VALID (${c.point_count} pts, RMSE ${(c.rmse ?? 0).toFixed(3)}px)`
        : 'CALIBRATION — REQUIRED' },
    { id: 'cam', state: hw.camera_detected ? 'ok' : 'warn',
      detail: hw.camera_detected ? 'CAMERA — DETECTED' : 'CAMERA — NOT FOUND' },
    { id: 'prt', state: hw.printer_configured ? 'ok' : 'warn',
      detail: hw.printer_configured ? 'PRINTER — CONFIGURED' : 'PRINTER — NOT CONFIGURED' },
    { id: 'orc', state: hw.orca_slicer ? 'ok' : 'warn',
      detail: hw.orca_slicer ? 'ORCA SLICER — FOUND' : 'ORCA SLICER — NOT FOUND' },
    { id: 'osc', state: hw.openscad ? 'ok' : 'warn',
      detail: hw.openscad ? 'OPENSCAD — FOUND' : 'OPENSCAD — NOT FOUND' },
    { id: 'cf',  state: sv.cf_api_key_set ? 'ok' : 'warn',
      detail: sv.cf_api_key_set ? 'CLOUDFLARE API — CONFIGURED' : 'CLOUDFLARE API — KEY MISSING' },
  ]
}

interface Props {
  health: HealthResponse | null
  error: string | null
}

export default function BootChecklist({ health, error }: Props) {
  const checks = build(health, error)
  return (
    <div className="text-center">
      <h2 className="text-[11px] tracking-[0.2em] text-j-muted uppercase mb-4 font-sans">
        System // Boot Sequence
      </h2>
      <ul className="flex flex-col gap-1.5 text-left min-w-[320px]">
        {checks.map((chk) => (
          <li key={chk.id}
            className={`flex items-center gap-2.5 font-mono text-[12px] tracking-[0.08em] uppercase ${COLOR[chk.state]}`}
          >
            <span className="w-[14px] text-center flex-shrink-0">{ICON[chk.state]}</span>
            {chk.detail}
          </li>
        ))}
      </ul>
    </div>
  )
}
