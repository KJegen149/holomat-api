import { useEffect, useRef } from 'react'

export type ParticleMode = 'idle' | 'listening' | 'speaking'

interface Props {
  mode?: ParticleMode
  className?: string
}

interface Particle {
  ox: number; oy: number; oz: number
  halo: number; seed: number
}
interface OuterPoint {
  r: number; a: number; b: number; s: number; speed: number
}

/* Canvas-2D particle sphere — port of the Phase-13 mockup.
   Audio level rises in 'speaking', dips in 'listening', decays in 'idle'.
   The sphere breathes, drifting halo particles surround it, and ripples
   pulse outward while speaking. */
export default function ParticleSphere({ mode = 'idle', className }: Props) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const modeRef = useRef<ParticleMode>(mode)

  useEffect(() => { modeRef.current = mode }, [mode])

  useEffect(() => {
    const wrap = wrapRef.current
    const canvas = canvasRef.current
    if (!wrap || !canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let w = 0, h = 0
    const N = 750
    const particles: Particle[] = []
    for (let i = 0; i < N; i++) {
      const phi = Math.acos(1 - 2 * (i + 0.5) / N)
      const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 0.5)
      particles.push({
        ox: Math.sin(phi) * Math.cos(theta),
        oy: Math.sin(phi) * Math.sin(theta),
        oz: Math.cos(phi),
        halo: Math.random() * 1.0 + 0.6,
        seed: Math.random() * Math.PI * 2,
      })
    }
    const outer: OuterPoint[] = []
    for (let i = 0; i < 220; i++) {
      outer.push({
        r: 1.05 + Math.random() * 0.6,
        a: Math.random() * Math.PI * 2,
        b: (Math.random() - 0.5) * Math.PI,
        s: 0.6 + Math.random() * 0.5,
        speed: 0.0002 + Math.random() * 0.0004,
      })
    }

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const r = wrap!.getBoundingClientRect()
      w = r.width; h = r.height
      canvas!.width = w * dpr
      canvas!.height = h * dpr
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(wrap)

    const t0 = performance.now()
    let audioLevel = 0
    let frame = 0
    let alive = true

    function render(t: number) {
      if (!w || !h) return
      ctx!.clearRect(0, 0, w, h)
      const cx = w / 2, cy = h / 2
      const baseR = Math.min(w, h) * 0.26

      const m = modeRef.current
      if (m === 'speaking') {
        const env = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t * 0.012))
        const flicker = 0.7 + 0.3 * Math.sin(t * 0.04 + Math.sin(t * 0.018) * 4)
        audioLevel = env * flicker
      } else if (m === 'listening') {
        audioLevel = 0.15 + 0.1 * Math.sin(t * 0.008)
      } else {
        audioLevel *= 0.95
      }

      const breath = 1 + Math.sin(t * 0.0008) * 0.035 + audioLevel * 0.18
      const pulse = baseR * breath
      const ry = t * 0.00025
      const rx = Math.sin(t * 0.00018) * 0.35
      const cosY = Math.cos(ry), sinY = Math.sin(ry)
      const cosX = Math.cos(rx), sinX = Math.sin(rx)

      const halo = ctx!.createRadialGradient(cx, cy, 0, cx, cy, pulse * 1.5)
      halo.addColorStop(0,   `rgba(0, 220, 255, ${0.28 + audioLevel * 0.25})`)
      halo.addColorStop(0.35,`rgba(80, 130, 220, ${0.12 + audioLevel * 0.12})`)
      halo.addColorStop(1,   'rgba(0, 0, 0, 0)')
      ctx!.fillStyle = halo
      ctx!.fillRect(0, 0, w, h)

      for (const p of outer) {
        p.a += p.speed
        const x = Math.cos(p.a) * Math.cos(p.b) * pulse * p.r
        const y = Math.sin(p.b) * pulse * p.r
        const z = Math.sin(p.a) * Math.cos(p.b)
        const depth = (z + 1) / 2
        ctx!.fillStyle = `rgba(0, ${(180 + depth * 50) | 0}, ${(230 + depth * 25) | 0}, ${0.15 + depth * 0.25})`
        ctx!.beginPath()
        ctx!.arc(cx + x, cy + y, p.s, 0, Math.PI * 2)
        ctx!.fill()
      }

      const pts: { sx: number; sy: number; sz: number; halo: number }[] = []
      for (const p of particles) {
        const x = p.ox * cosY + p.oz * sinY
        const z = -p.ox * sinY + p.oz * cosY
        const y = p.oy
        const y2 = y * cosX - z * sinX
        const z2 = y * sinX + z * cosX
        const wobble = 1 + Math.sin(t * 0.001 + p.seed) * 0.018 + audioLevel * 0.08 * Math.sin(p.seed + t * 0.004)
        const r = pulse * wobble
        pts.push({ sx: cx + x * r, sy: cy + y2 * r, sz: z2, halo: p.halo })
      }
      pts.sort((a, b) => a.sz - b.sz)
      for (const pt of pts) {
        const depth = (pt.sz + 1) / 2
        const size = 0.5 + depth * 1.7 * pt.halo
        const violetMix = 1 - depth
        const rC = (0 + violetMix * 80) | 0
        const gC = (180 + depth * 75) | 0
        const bC = (220 + depth * 35) | 0
        const aC = 0.18 + depth * 0.7
        ctx!.fillStyle = `rgba(${rC}, ${gC}, ${bC}, ${aC})`
        ctx!.beginPath()
        ctx!.arc(pt.sx, pt.sy, size, 0, Math.PI * 2)
        ctx!.fill()
      }

      if (m === 'speaking') {
        for (let i = 0; i < 3; i++) {
          const phase = (t * 0.0008 + i / 3) % 1
          const rr = pulse * (1 + phase * 1.6)
          const aa = (1 - phase) * 0.35
          ctx!.strokeStyle = `rgba(0, 220, 255, ${aa})`
          ctx!.lineWidth = 1.2
          ctx!.beginPath()
          ctx!.arc(cx, cy, rr, 0, Math.PI * 2)
          ctx!.stroke()
        }
      }
    }

    const loop = () => {
      if (!alive) return
      render(performance.now() - t0)
      frame = requestAnimationFrame(loop)
    }
    frame = requestAnimationFrame(loop)

    return () => {
      alive = false
      cancelAnimationFrame(frame)
      ro.disconnect()
    }
  }, [])

  return (
    <div ref={wrapRef} className={className ?? 'absolute inset-0'}>
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
    </div>
  )
}
