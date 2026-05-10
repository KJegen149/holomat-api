interface Props {
  label?: string
  sublabel?: string
}

export default function RadarAnimation({ label = 'CORE', sublabel = 'ACTIVE' }: Props) {
  return (
    <div className="relative w-[280px] h-[280px] flex items-center justify-center flex-shrink-0">
      {/* Crosshair */}
      <div className="absolute w-px h-full bg-j-cdim opacity-40" />
      <div className="absolute h-px w-full bg-j-cdim opacity-40" />

      {/* Rings */}
      <div className="absolute w-[280px] h-[280px] rounded-full border border-dashed border-j-cdim opacity-30 animate-spin-slow" />
      <div className="absolute w-[200px] h-[200px] rounded-full border border-dashed border-j-cdim opacity-50 animate-spin-rslw" />
      <div className="absolute w-[120px] h-[120px] rounded-full border border-j-cdim opacity-70 animate-spin-med" />
      <div className="absolute w-[56px]  h-[56px]  rounded-full border border-j-cyan animate-spin-rmed" />

      {/* Sweep */}
      <div
        className="absolute w-[280px] h-[280px] rounded-full animate-radar-sweep"
        style={{ background: 'conic-gradient(from 0deg, transparent 330deg, rgba(0,200,232,0.15) 360deg)' }}
      />

      {/* Ticks */}
      <div className="absolute top-3 left-1/2 -translate-x-1/2 w-6 h-0.5 bg-j-cyan animate-tick-blink" />
      <div
        className="absolute bottom-3 left-1/2 w-6 h-0.5 bg-j-cyan animate-tick-blink"
        style={{ transform: 'translateX(-50%) rotate(180deg)', animationDelay: '2s' }}
      />

      {/* Core label */}
      <div className="relative z-10 text-center">
        <div className="text-j-cyan font-bold text-[13px] tracking-[0.2em] uppercase font-sans">{label}</div>
        <div className="text-j-muted text-[10px] tracking-[0.15em] uppercase mt-0.5 font-sans">{sublabel}</div>
      </div>
    </div>
  )
}
