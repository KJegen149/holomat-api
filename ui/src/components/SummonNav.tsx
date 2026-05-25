import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Scan, Image, Boxes, Printer, Home, Settings,
  type LucideIcon,
} from 'lucide-react'

interface NavItem {
  path: string
  label: string
  icon: LucideIcon
}

const NAV_ITEMS: NavItem[] = [
  { path: '/',               label: 'Dashboard',     icon: LayoutDashboard },
  { path: '/scanner',        label: 'Scanner',       icon: Scan },
  { path: '/gallery',        label: 'Gallery',       icon: Image },
  { path: '/models',         label: 'Models',        icon: Boxes },
  { path: '/print',          label: 'Print',         icon: Printer },
  { path: '/home-assistant', label: 'Home Assistant',icon: Home },
  { path: '/settings',       label: 'Settings',      icon: Settings },
]

/* Selector that matches the regions where long-press should NOT summon the
   menu — anything interactive, plus chrome elements that own their own
   pointer handling. */
const NON_TRIGGER_SELECTOR =
  'button, input, textarea, select, a, [role="button"], [role="link"],' +
  ' [contenteditable="true"], canvas, .summon-orb-corner, .summon-host'

const LONG_PRESS_MS = 380
const RING_FRACTION = 0.22   // ring radius = min(viewport) * this
const ITEM_SIZE = 78          // px

/* The "Orbital Summon" nav.
   - Long-press anywhere on <main> for ~380ms
   - Or tap the always-visible corner pulse orb
   - Or dispatch CustomEvent('holomat:open-menu') from anywhere (PR-4 wires this
     to the Wyoming voice intent)
   On tap of an item: the item pulses brighter, the ring fades out, then the
   route changes. */
export default function SummonNav() {
  const [open, setOpen] = useState(false)
  const [pulsingId, setPulsingId] = useState<string | null>(null)
  const [viewport, setViewport] = useState({ w: window.innerWidth, h: window.innerHeight })
  const navigate = useNavigate()
  const location = useLocation()

  // Track viewport for orbit radius
  useEffect(() => {
    const onResize = () => setViewport({ w: window.innerWidth, h: window.innerHeight })
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // Close on route change (defensive; we usually close before nav fires)
  useEffect(() => { setOpen(false); setPulsingId(null) }, [location.pathname])

  // Esc closes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Voice trigger — PR-4 dispatches this from the voice bridge
  useEffect(() => {
    const onOpen = () => setOpen(true)
    window.addEventListener('holomat:open-menu', onOpen as EventListener)
    return () => window.removeEventListener('holomat:open-menu', onOpen as EventListener)
  }, [])

  // Long-press on <main>
  const pressTimer = useRef<number | null>(null)
  useEffect(() => {
    const main = document.querySelector('main')
    if (!main) return

    const onDown = (e: PointerEvent) => {
      if (open) return
      const target = e.target as Element | null
      if (target && target.closest(NON_TRIGGER_SELECTOR)) return
      // Right-click / middle-click → no
      if (e.button !== 0 && e.pointerType === 'mouse') return
      if (pressTimer.current != null) window.clearTimeout(pressTimer.current)
      pressTimer.current = window.setTimeout(() => setOpen(true), LONG_PRESS_MS)
    }
    const cancel = () => {
      if (pressTimer.current != null) {
        window.clearTimeout(pressTimer.current)
        pressTimer.current = null
      }
    }

    main.addEventListener('pointerdown', onDown as EventListener)
    main.addEventListener('pointerup', cancel as EventListener)
    main.addEventListener('pointerleave', cancel as EventListener)
    main.addEventListener('pointercancel', cancel as EventListener)
    main.addEventListener('pointermove', cancel as EventListener)  // any drag cancels
    return () => {
      cancel()
      main.removeEventListener('pointerdown', onDown as EventListener)
      main.removeEventListener('pointerup', cancel as EventListener)
      main.removeEventListener('pointerleave', cancel as EventListener)
      main.removeEventListener('pointercancel', cancel as EventListener)
      main.removeEventListener('pointermove', cancel as EventListener)
    }
  }, [open])

  const pick = (path: string) => {
    setPulsingId(path)
    window.setTimeout(() => setOpen(false), 260)
    window.setTimeout(() => {
      setPulsingId(null)
      if (path !== location.pathname) navigate(path)
    }, 320)
  }

  const radius = Math.min(viewport.w, viewport.h) * RING_FRACTION
  const ringDiameter = radius * 2

  return (
    <>
      {/* Corner pulse orb — discoverability cue, always visible */}
      <button
        type="button"
        aria-label="Open navigation"
        onClick={() => setOpen(true)}
        className="summon-orb-corner fixed bottom-5 right-5 z-30
                   w-14 h-14 rounded-full flex items-center justify-center
                   text-j-cyan cursor-pointer animate-j-orb-pulse
                   border border-j-border/55"
        style={{
          background:
            'radial-gradient(circle at 30% 30%, rgba(0,220,255,0.40), rgba(0,220,255,0.05))',
        }}
      >
        <LayoutDashboard size={22} strokeWidth={1.5} />
      </button>

      {/* Backdrop */}
      <div
        onClick={() => setOpen(false)}
        className={`fixed inset-0 z-40 transition-opacity duration-200
                    ${open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
        style={{
          background: 'rgba(5, 6, 9, 0.4)',
          backdropFilter: 'blur(4px)',
          WebkitBackdropFilter: 'blur(4px)',
        }}
      />

      {/* Summon host — centered on screen */}
      <div
        className="summon-host fixed left-1/2 top-1/2 z-50 pointer-events-none"
        style={{ width: 0, height: 0, transform: 'translate(-50%, -50%)' }}
      >
        {/* Faint guide ring drawn at the orbit radius */}
        <div
          className="absolute left-1/2 top-1/2 rounded-full transition-all duration-[360ms]"
          style={{
            width: open ? ringDiameter : 0,
            height: open ? ringDiameter : 0,
            transform: 'translate(-50%, -50%)',
            border: open ? '1px dashed rgba(0, 220, 255, 0.15)' : '1px dashed rgba(0, 220, 255, 0)',
            boxShadow: open ? 'inset 0 0 40px rgba(0, 220, 255, 0.05)' : 'none',
            transitionTimingFunction: 'cubic-bezier(.2,.8,.2,1)',
          }}
        />

        {NAV_ITEMS.map((item, i) => {
          const angle = (i / NAV_ITEMS.length) * Math.PI * 2 - Math.PI / 2
          const x = open ? Math.cos(angle) * radius : 0
          const y = open ? Math.sin(angle) * radius : 0
          const isPulsing = pulsingId === item.path
          const isActive = location.pathname === item.path
          const scale = isPulsing ? 1.18 : open ? 1 : 0.6
          const Icon = item.icon

          return (
            <button
              key={item.path}
              type="button"
              onClick={(e) => { e.stopPropagation(); pick(item.path) }}
              className={`absolute rounded-full flex flex-col items-center justify-center gap-1
                          text-j-text border backdrop-blur-j
                          transition-all duration-[280ms]
                          ${open ? 'pointer-events-auto' : 'pointer-events-none'}
                          ${isActive
                              ? 'border-j-cyan text-j-cyan bg-j-cyan/15'
                              : 'border-j-border/20 bg-j-surf-hi/80 hover:text-j-cyan hover:border-j-border/55'}
                         `}
              style={{
                left: '50%', top: '50%',
                width: ITEM_SIZE, height: ITEM_SIZE,
                marginLeft: -ITEM_SIZE / 2, marginTop: -ITEM_SIZE / 2,
                transform: `translate(${x}px, ${y}px) scale(${scale})`,
                opacity: open ? 1 : 0,
                transitionTimingFunction: 'cubic-bezier(.2,.8,.2,1)',
                boxShadow: isPulsing
                  ? '0 0 48px rgba(0, 220, 255, 0.7), inset 0 0 22px rgba(0, 220, 255, 0.3)'
                  : isActive
                    ? '0 0 36px rgba(0, 220, 255, 0.45), inset 0 0 18px rgba(0, 220, 255, 0.22)'
                    : '0 6px 22px rgba(0, 0, 0, 0.45)',
              }}
            >
              <Icon size={22} strokeWidth={1.5} />
              <span
                className="absolute top-full left-1/2 -translate-x-1/2 mt-2 whitespace-nowrap
                           text-[9px] uppercase tracking-[0.22em] transition-opacity duration-200"
                style={{ opacity: open ? 0.85 : 0, color: isActive ? 'rgb(0 220 255)' : undefined }}
              >
                {item.label}
              </span>
            </button>
          )
        })}
      </div>
    </>
  )
}
