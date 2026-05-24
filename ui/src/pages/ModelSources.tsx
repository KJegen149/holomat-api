/**
 * Phase 11 — Model Sources tab.
 *
 * Browser/manager for the shared STL pool at scan_data/stls/. Every Phase 11
 * inlet (Meshy retrieval, Thingiverse, MakerWorld, TinkerCad export) lands a
 * file here; this is where the user sees, queues, and deletes them.
 *
 * The Print tab keeps its own quick STL dropdown — this is the fuller view.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Boxes, RefreshCw, Trash2, Printer, Loader2, AlertTriangle, X,
  Box, Globe, Hammer, ExternalLink, Pencil, Sparkles, Search,
} from 'lucide-react'
import ThingiverseSearchModal from '../components/ThingiverseSearchModal'
import {
  fetchSourceStls, deleteSourceStl,
  queuePrintJob, fetchPrintProfiles,
  fetchMeshyJobs, cancelMeshyJob,
  type ModelSourceStl, type ModelSource, type PrintProfile,
  type MeshyJob, type MeshyJobState,
} from '../api/client'

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function fmtDate(epochSec: number): string {
  const d = new Date(epochSec * 1000)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
    ' ' + d.toTimeString().slice(0, 5)
}

const SOURCE_LABEL: Record<ModelSource, string> = {
  openscad:    'OPENSCAD',
  samba:       'SAMBA',
  meshy:       'MESHY',
  thingiverse: 'THINGIVERSE',
  makerworld:  'MAKERWORLD',
  tinkercad:   'TINKERCAD',
  unknown:     'LOCAL',
}

const SOURCE_COLOR: Record<ModelSource, string> = {
  openscad:    'text-j-cyan   border-j-cyan/40',
  samba:       'text-j-muted  border-j-border',
  meshy:       'text-j-amber  border-j-amber/40',
  thingiverse: 'text-j-green  border-j-green/40',
  makerworld:  'text-j-amber  border-j-amber/40',
  tinkercad:   'text-j-cyan   border-j-cyan/40',
  unknown:     'text-j-cdim   border-j-border',
}

// ── STL card ────────────────────────────────────────────────────────────────

function StlCard({
  stl,
  profiles,
  onQueue,
  onDelete,
}: {
  stl: ModelSourceStl
  profiles: PrintProfile[]
  onQueue: (filename: string, profile: string) => Promise<void>
  onDelete: (filename: string) => Promise<void>
}) {
  const [busy, setBusy] = useState<'idle' | 'queueing' | 'deleting'>('idle')
  const [msg, setMsg] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const defaultProfile = profiles.find(p => p.id === 'standard')?.id ?? profiles[0]?.id ?? 'standard'

  async function handleQueue() {
    setBusy('queueing')
    setMsg(null)
    try {
      await onQueue(stl.filename, defaultProfile)
      setMsg('Queued')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Queue failed')
    } finally {
      setBusy('idle')
    }
  }

  async function handleDelete() {
    setBusy('deleting')
    try {
      await onDelete(stl.filename)
      // card disappears on parent refresh — no msg needed
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Delete failed')
      setBusy('idle')
      setConfirmDelete(false)
    }
  }

  return (
    <div className="bg-j-surf border border-j-border rounded-sm overflow-hidden flex flex-col group hover:border-j-cyan/40 transition-colors">
      {/* Thumb (only if sidecar provides one — placeholder otherwise) */}
      <div className="relative bg-black/30 aspect-square flex items-center justify-center overflow-hidden">
        {stl.thumbnail_url ? (
          <img src={stl.thumbnail_url} alt={stl.filename} className="w-full h-full object-cover" />
        ) : (
          <Box size={36} strokeWidth={1} className="text-j-cdim" />
        )}
        <span className={`absolute bottom-1.5 left-1.5 text-[8px] font-mono tracking-[0.15em] uppercase
                          px-1.5 py-0.5 rounded-sm bg-j-bg/85 border ${SOURCE_COLOR[stl.source]}`}>
          {SOURCE_LABEL[stl.source]}
        </span>
      </div>

      {/* Info */}
      <div className="p-2.5 flex flex-col gap-1.5 flex-1">
        <div className="font-sans text-[11px] text-j-text truncate" title={stl.filename}>
          {stl.stem}
        </div>
        <div className="flex justify-between font-mono text-[9px] text-j-muted">
          <span>{fmtSize(stl.size_bytes)}</span>
          <span>{fmtDate(stl.modified_at)}</span>
        </div>

        {stl.external_url && (
          <a
            href={stl.external_url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 font-mono text-[9px] text-j-cyan/80 hover:text-j-cyan"
          >
            <ExternalLink size={9} /> source
          </a>
        )}

        {/* Actions */}
        <div className="flex gap-1.5 mt-auto pt-1">
          <button
            onClick={handleQueue}
            disabled={busy !== 'idle'}
            title="Add to print queue with the Standard profile"
            className="flex-1 flex items-center justify-center gap-1 py-1.5
                       border border-j-border text-j-muted hover:text-j-cyan hover:border-j-cyan
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors rounded-sm
                       font-mono text-[10px] tracking-[0.05em] uppercase"
          >
            {busy === 'queueing'
              ? <Loader2 size={11} className="animate-spin" />
              : <><Printer size={11} /> Queue</>}
          </button>
          {!confirmDelete ? (
            <button
              onClick={() => setConfirmDelete(true)}
              disabled={busy !== 'idle'}
              title="Delete from disk"
              className="px-2 py-1.5 border border-j-border text-j-muted hover:text-j-red hover:border-j-red
                         disabled:opacity-40 transition-colors rounded-sm"
            >
              <Trash2 size={11} />
            </button>
          ) : (
            <>
              <button
                onClick={handleDelete}
                disabled={busy !== 'idle'}
                className="px-2 py-1.5 border border-j-red text-j-red hover:bg-j-red/10
                           transition-colors rounded-sm font-mono text-[10px]"
              >
                {busy === 'deleting' ? <Loader2 size={11} className="animate-spin" /> : 'Confirm'}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={busy !== 'idle'}
                className="px-2 py-1.5 border border-j-border text-j-muted hover:text-j-text
                           transition-colors rounded-sm"
              >
                <X size={11} />
              </button>
            </>
          )}
        </div>

        {msg && (
          <p className={`font-mono text-[9px] ${
            msg === 'Queued' ? 'text-j-green' : 'text-j-amber'
          } truncate`}>{msg}</p>
        )}
      </div>
    </div>
  )
}

// ── Meshy retrievals (live pending jobs panel) ──────────────────────────────

const MESHY_STATE_LABEL: Record<MeshyJobState, string> = {
  pending:     'PENDING',
  polling:     'POLLING',
  downloading: 'DOWNLOADING',
  done:        'DONE',
  failed:      'FAILED',
  cancelled:   'CANCELLED',
}

const MESHY_STATE_COLOR: Record<MeshyJobState, string> = {
  pending:     'text-j-muted',
  polling:     'text-j-amber',
  downloading: 'text-j-cyan',
  done:        'text-j-green',
  failed:      'text-j-red',
  cancelled:   'text-j-cdim',
}

function MeshyJobRow({ job, onCancel }: { job: MeshyJob; onCancel: (id: string) => void }) {
  const isActive = ['pending', 'polling', 'downloading'].includes(job.state)
  return (
    <div className="border border-j-border rounded-sm px-2 py-1.5 space-y-1">
      <div className="flex items-center gap-1.5">
        <span className="font-sans text-[10px] text-j-text truncate flex-1" title={job.source_filename}>
          {job.source_filename}
        </span>
        <span className={`font-mono text-[8px] tracking-[0.1em] ${MESHY_STATE_COLOR[job.state]}`}>
          {MESHY_STATE_LABEL[job.state]}
        </span>
        {isActive && (
          <button
            onClick={() => onCancel(job.id)}
            className="text-j-muted hover:text-j-red transition-colors"
            title="Cancel"
          >
            <X size={10} />
          </button>
        )}
      </div>
      {isActive && (
        <div className="h-0.5 bg-j-border rounded-full overflow-hidden">
          <div
            className="h-full bg-j-cyan transition-all"
            style={{ width: `${job.progress}%` }}
          />
        </div>
      )}
      {job.error && (
        <div className="font-mono text-[8px] text-j-red break-all">{job.error}</div>
      )}
    </div>
  )
}

function MeshyRetrievals({
  active,
  onCancel,
}: {
  active: MeshyJob[]
  onCancel: (id: string) => void
}) {
  return (
    <div className="border border-j-border rounded-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 font-mono text-[9px] text-j-cdim tracking-[0.2em] uppercase">
          <Sparkles size={10} className="text-j-amber" /> Meshy Retrievals
        </div>
        {active.length > 0 && (
          <span className="font-mono text-[9px] text-j-cyan">{active.length} active</span>
        )}
      </div>
      {active.length === 0 ? (
        <p className="font-mono text-[9px] text-j-cdim leading-relaxed">
          Submit images from the Gallery tab — finished STLs land here.
        </p>
      ) : (
        <div className="space-y-1.5">
          {active.map(j => <MeshyJobRow key={j.id} job={j} onCancel={onCancel} />)}
        </div>
      )}
    </div>
  )
}

// ── Other inlets (still placeholders) ───────────────────────────────────────

function OtherInlets({ onOpenThingiverse }: { onOpenThingiverse: () => void }) {
  const placeholders: { label: string; icon: typeof Box; tip: string }[] = [
    { label: 'MakerWorld',  icon: Globe,  tip: 'Browse MakerWorld — coming soon' },
    { label: 'TinkerCad',   icon: Pencil, tip: 'Open TinkerCad — coming soon' },
  ]
  return (
    <div className="border border-j-border rounded-sm p-3">
      <div className="font-mono text-[9px] text-j-cdim tracking-[0.2em] uppercase mb-2">
        Other Inlets
      </div>
      <div className="grid grid-cols-1 gap-1.5">
        <button
          onClick={onOpenThingiverse}
          className="flex items-center justify-center gap-1.5 py-1.5 border border-j-border
                     text-j-muted hover:text-j-cyan hover:border-j-cyan transition-colors rounded-sm
                     font-mono text-[10px] tracking-[0.05em] uppercase"
        >
          <Search size={11} /> Thingiverse
        </button>
        {placeholders.map(({ label, icon: Icon, tip }) => (
          <button
            key={label}
            disabled
            title={tip}
            className="flex items-center justify-center gap-1.5 py-1.5 border border-j-border
                       text-j-cdim opacity-50 cursor-not-allowed rounded-sm
                       font-mono text-[10px] tracking-[0.05em] uppercase"
          >
            <Icon size={11} /> {label}
          </button>
        ))}
      </div>
      <p className="font-mono text-[9px] text-j-cdim mt-2 leading-relaxed">
        Drop into <span className="text-j-muted">\\KJLC-AI-01\HolomatSTL</span> for
        immediate ingestion.
      </p>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function ModelSources() {
  const [stls, setStls] = useState<ModelSourceStl[]>([])
  const [profiles, setProfiles] = useState<PrintProfile[]>([])
  const [meshyActive, setMeshyActive] = useState<MeshyJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [thingiverseOpen, setThingiverseOpen] = useState(false)
  // Use a ref so the WS callback can refresh without re-subscribing on every state change
  const reloadRef = useRef<() => void>(() => {})

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [r, p, m] = await Promise.all([
        fetchSourceStls(),
        fetchPrintProfiles(),
        fetchMeshyJobs(),
      ])
      setStls(r.stls)
      setProfiles(p.profiles)
      setMeshyActive(m.active)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { reloadRef.current = load }, [load])

  useEffect(() => {
    load()
    const id = setInterval(load, 15_000)
    return () => clearInterval(id)
  }, [load])

  // Listen for live Meshy job updates → refresh the STL grid when one finishes
  useEffect(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws`)
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data as string) as { type?: string; state?: MeshyJobState }
        if (d.type === 'meshy_job_update') {
          // A finished/cancelled job means the active list shrinks and a new STL may exist
          reloadRef.current()
        }
      } catch { /* ignore */ }
    }
    return () => ws.close()
  }, [])

  const handleQueue = useCallback(async (filename: string, profile: string) => {
    await queuePrintJob(filename, profile)
  }, [])

  const handleDelete = useCallback(async (filename: string) => {
    await deleteSourceStl(filename)
    setStls(prev => prev.filter(s => s.filename !== filename))
  }, [])

  const handleCancelMeshy = useCallback(async (jobId: string) => {
    try {
      await cancelMeshyJob(jobId)
      setMeshyActive(prev => prev.filter(j => j.id !== jobId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Cancel failed')
    }
  }, [])

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: STL grid */}
      <div className="flex-1 flex flex-col overflow-hidden border-r border-j-border">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-j-border bg-j-surf flex-shrink-0">
          <div className="flex items-center gap-2">
            <Boxes size={14} className="text-j-cyan" />
            <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
              MODEL SOURCES
            </span>
            <span className="font-mono text-[10px] text-j-cdim">
              ({stls.length})
            </span>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="text-j-muted hover:text-j-text transition-colors disabled:opacity-40"
            title="Refresh"
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-3 border border-j-red bg-j-red/5 rounded-sm p-3
                            font-mono text-[10px] text-j-red flex items-start gap-2">
              <AlertTriangle size={11} className="mt-0.5 flex-shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          )}

          {loading && stls.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={22} className="animate-spin text-j-cyan" />
            </div>
          ) : stls.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
              <Hammer size={40} strokeWidth={1} className="text-j-cdim" />
              <div>
                <p className="text-j-muted text-sm">No models in the pool</p>
                <p className="text-j-cdim text-xs mt-1">
                  Generate an OpenSCAD case from the Scanner,<br/>
                  or drop a .stl into \\KJLC-AI-01\HolomatSTL.
                </p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
              {stls.map(stl => (
                <StlCard
                  key={stl.filename}
                  stl={stl}
                  profiles={profiles}
                  onQueue={handleQueue}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: import sources sidebar */}
      <div className="w-[260px] flex flex-col bg-j-surf flex-shrink-0 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-j-border flex-shrink-0">
          <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
            INLETS
          </span>
        </div>
        <div className="flex-1 p-4 overflow-y-auto space-y-3">
          <MeshyRetrievals active={meshyActive} onCancel={handleCancelMeshy} />
          <OtherInlets onOpenThingiverse={() => setThingiverseOpen(true)} />
        </div>
      </div>

      <ThingiverseSearchModal
        open={thingiverseOpen}
        onClose={() => setThingiverseOpen(false)}
        onImported={load}
      />
    </div>
  )
}
