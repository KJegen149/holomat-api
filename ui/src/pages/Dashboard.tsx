import RadarAnimation from '../components/RadarAnimation'
import BootChecklist from '../components/BootChecklist'
import type { HealthResponse } from '../api/client'

interface Props {
  health: HealthResponse | null
  healthError: string | null
}

export default function Dashboard({ health, healthError }: Props) {
  const calibValid = health?.calibration.valid ?? false
  const radarSub   = healthError ? 'OFFLINE' : health ? 'ACTIVE' : 'INITIALIZING'

  return (
    <div className="flex h-full overflow-y-auto">
      <div className="flex-1 flex flex-col items-center justify-center gap-8 p-10">
        <RadarAnimation label="CORE" sublabel={radarSub} />
        <BootChecklist health={health} error={healthError} />

        {health && !calibValid && (
          <div className="max-w-[480px] w-full bg-j-amber/5 border border-j-amber rounded-sm px-6 py-4 text-center">
            <h3 className="text-j-amber font-bold text-[13px] tracking-[0.15em] uppercase mb-2 font-sans">
              ⚠ Calibration Required
            </h3>
            <p className="text-j-muted text-[11px] tracking-[0.03em] leading-relaxed font-sans">
              No valid calibration data found.<br />
              Place the ChArUco calibration board on the mat and proceed to the calibration wizard.<br />
              The system cannot enter normal mode until calibration is complete.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
