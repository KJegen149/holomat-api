import { useState, useEffect, useCallback } from 'react'
import {
  Image, RefreshCw, Trash2, Box, Code2, AlertTriangle, Info,
  CheckCircle, Loader2, Download,
} from 'lucide-react'
import {
  fetchGallery, deleteGalleryItem, galleryImageUrl,
  galleryGenerate3d, galleryGenerateSvg,
  fetchMeshyJobs,
  type GalleryItem, type MeshyJob,
} from '../api/client'

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmtSize(bytes: number | null): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) +
    ' ' + d.toTimeString().slice(0, 5)
}

// ── SVG preview modal ───────────────────────────────────────────────────────

function SvgModal({ svg, onClose }: { svg: string; onClose: () => void }) {
  function download() {
    const blob = new Blob([svg], { type: 'image/svg+xml' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'gallery-export.svg'
    a.click()
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className="bg-j-surf border border-j-border rounded-lg p-4 max-w-2xl w-full mx-4 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <span className="text-j-cyan font-mono text-sm tracking-widest">SVG OUTPUT</span>
          <div className="flex gap-2">
            <button
              onClick={download}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-j-border text-j-muted hover:text-j-text hover:border-j-cyan transition-colors"
            >
              <Download size={12} /> Download
            </button>
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs rounded border border-j-border text-j-muted hover:text-j-text transition-colors"
            >
              Close
            </button>
          </div>
        </div>
        <div className="bg-white rounded p-3 flex items-center justify-center min-h-48">
          <img
            src={`data:image/svg+xml,${encodeURIComponent(svg)}`}
            alt="Generated SVG"
            className="max-w-full max-h-96"
          />
        </div>
      </div>
    </div>
  )
}

// ── Gallery card ─────────────────────────────────────────────────────────────

function GalleryCard({
  item,
  meshyJob,
  onDelete,
  onSvgReady,
}: {
  item: GalleryItem
  meshyJob: MeshyJob | undefined
  onDelete: (id: string) => void
  onSvgReady: (svg: string) => void
}) {
  const [deleting, setDeleting] = useState(false)
  const [gen3d, setGen3d] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [gen3dMsg, setGen3dMsg] = useState<string | null>(null)
  const [genSvg, setGenSvg] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [imgError, setImgError] = useState(false)

  async function handleDelete() {
    setDeleting(true)
    try {
      await deleteGalleryItem(item.id)
      onDelete(item.id)
    } catch (e) {
      setDeleting(false)
    }
  }

  async function handleGenerate3d() {
    setGen3d('loading')
    setGen3dMsg(null)
    try {
      await galleryGenerate3d(item.id)
      setGen3d('done')
      // The MeshyJob WS updates take over from here; show progress in a dedicated row.
    } catch (e) {
      setGen3d('error')
      setGen3dMsg(e instanceof Error ? e.message : 'Failed')
    }
  }

  // Render live Meshy progress / outcome when the parent has a job for this item.
  const meshyRow = meshyJob && (() => {
    const isActive = ['pending', 'polling', 'downloading'].includes(meshyJob.state)
    const labelMap: Record<string, string> = {
      pending:     'Queued',
      polling:     `Generating ${meshyJob.progress}%`,
      downloading: 'Downloading STL',
      done:        `Saved: ${meshyJob.stl_filename ?? ''}`,
      failed:      meshyJob.error || 'Failed',
      cancelled:   'Cancelled',
    }
    const colorMap: Record<string, string> = {
      pending:     'text-j-muted',
      polling:     'text-j-amber',
      downloading: 'text-j-cyan',
      done:        'text-j-green',
      failed:      'text-j-red',
      cancelled:   'text-j-cdim',
    }
    return (
      <div className="space-y-1">
        <div className={`flex items-center gap-1 text-[10px] font-mono ${colorMap[meshyJob.state]}`}>
          {isActive && <Loader2 size={10} className="animate-spin" />}
          <span className="truncate">{labelMap[meshyJob.state]}</span>
        </div>
        {isActive && (
          <div className="h-0.5 bg-j-border rounded-full overflow-hidden">
            <div
              className="h-full bg-j-cyan transition-all"
              style={{ width: `${meshyJob.progress}%` }}
            />
          </div>
        )}
      </div>
    )
  })()

  async function handleGenerateSvg() {
    setGenSvg('loading')
    try {
      const r = await galleryGenerateSvg(item.id)
      setGenSvg('done')
      onSvgReady(r.svg)
    } catch (e) {
      setGenSvg('error')
    }
  }

  return (
    <div className="bg-j-surf border border-j-border rounded-lg overflow-hidden flex flex-col group hover:border-j-cyan/40 transition-colors">
      {/* Thumbnail */}
      <div className="relative bg-black/30 aspect-square flex items-center justify-center overflow-hidden">
        {!imgError ? (
          <img
            src={galleryImageUrl(item.id)}
            alt={item.filename}
            className="w-full h-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-j-muted">
            <Image size={32} className="opacity-30" />
            <span className="text-[10px]">Preview unavailable</span>
          </div>
        )}
        {/* Delete overlay */}
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="absolute top-2 right-2 p-1.5 rounded bg-black/60 text-j-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
          title="Delete"
        >
          {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
        </button>
        {/* Source badge */}
        <span className="absolute bottom-2 left-2 text-[9px] font-mono tracking-wider px-1.5 py-0.5 rounded bg-black/60 text-j-muted uppercase">
          {item.source}
        </span>
      </div>

      {/* Info */}
      <div className="p-3 flex flex-col gap-2 flex-1">
        <p className="text-j-text text-xs font-mono truncate" title={item.filename}>
          {item.filename}
        </p>
        <div className="flex justify-between text-[10px] text-j-muted font-mono">
          <span>{fmtSize(item.file_size)}</span>
          <span>{fmtDate(item.created_at)}</span>
        </div>

        {/* Actions */}
        <div className="flex gap-1.5 mt-auto pt-1">
          <button
            onClick={handleGenerate3d}
            disabled={gen3d === 'loading' || gen3d === 'done'}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 text-[10px] rounded border border-j-border text-j-muted hover:text-j-cyan hover:border-j-cyan disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Generate 3D model via Meshy"
          >
            {gen3d === 'loading' ? <Loader2 size={11} className="animate-spin" /> :
             gen3d === 'done' ? <CheckCircle size={11} className="text-j-green" /> :
             gen3d === 'error' ? <AlertTriangle size={11} className="text-j-amber" /> :
             <Box size={11} />}
            3D
          </button>
          <button
            onClick={handleGenerateSvg}
            disabled={genSvg === 'loading'}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 text-[10px] rounded border border-j-border text-j-muted hover:text-j-cyan hover:border-j-cyan disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Recreate as SVG via AI"
          >
            {genSvg === 'loading' ? <Loader2 size={11} className="animate-spin" /> :
             genSvg === 'done' ? <CheckCircle size={11} className="text-j-green" /> :
             genSvg === 'error' ? <AlertTriangle size={11} className="text-j-amber" /> :
             <Code2 size={11} />}
            SVG
          </button>
        </div>

        {meshyRow}
        {gen3dMsg && !meshyJob && (
          <p className={`text-[10px] font-mono ${gen3d === 'error' ? 'text-j-amber' : 'text-j-green'} truncate`}>
            {gen3dMsg}
          </p>
        )}
        {genSvg === 'error' && (
          <p className="text-[10px] font-mono text-j-amber">SVG generation failed</p>
        )}
      </div>
    </div>
  )
}

// ── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
      <Image size={48} className="text-j-muted opacity-30" />
      <div>
        <p className="text-j-muted text-sm mb-1">No images in the gallery</p>
        <p className="text-j-muted text-xs opacity-60">
          Drop images into the Samba share to auto-ingest them
        </p>
      </div>
      <div className="mt-2 p-3 rounded border border-j-border bg-j-surf text-left font-mono text-[11px] text-j-muted space-y-1">
        <div className="text-j-cyan mb-1">Windows</div>
        <div>\\KJLC-AI-01\HolomatGallery</div>
        <div className="text-j-cyan mt-2 mb-1">macOS / Linux</div>
        <div>smb://KJLC-AI-01/HolomatGallery</div>
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function Gallery() {
  const [items, setItems] = useState<GalleryItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [svgModal, setSvgModal] = useState<string | null>(null)
  // For each gallery item that has an in-flight or recent Meshy job, surface
  // the latest state on its card. Keyed by gallery_item_id.
  const [meshyByItem, setMeshyByItem] = useState<Record<string, MeshyJob>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetchGallery(100, 0)
      setItems(r.items)
      setTotal(r.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load gallery')
    } finally {
      setLoading(false)
    }
  }, [])

  const refreshMeshy = useCallback(async () => {
    try {
      const r = await fetchMeshyJobs()
      // Keep the most-recently-updated job per gallery item (active beats history).
      const map: Record<string, MeshyJob> = {}
      for (const j of [...r.history, ...r.active]) {
        if (j.gallery_item_id) map[j.gallery_item_id] = j
      }
      setMeshyByItem(map)
    } catch { /* non-fatal */ }
  }, [])

  useEffect(() => { load(); refreshMeshy() }, [load, refreshMeshy])

  // WebSocket listener for gallery_new + meshy_job_update events
  useEffect(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws`)
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data as string) as { type?: string; item?: GalleryItem }
        if (d.type === 'gallery_new' && d.item) {
          setItems(prev => [d.item!, ...prev])
          setTotal(prev => prev + 1)
        }
        if (d.type === 'meshy_job_update') {
          refreshMeshy()
        }
      } catch { /* ignore */ }
    }
    return () => ws.close()
  }, [refreshMeshy])

  function handleDelete(id: string) {
    setItems(prev => prev.filter(i => i.id !== id))
    setTotal(prev => Math.max(0, prev - 1))
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Image size={20} className="text-j-cyan" />
          <div>
            <h1 className="text-j-text font-mono tracking-wider text-base">GALLERY</h1>
            <p className="text-j-muted text-xs font-mono mt-0.5">
              SMB-watched image store — {total} item{total !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-xs rounded border border-j-border text-j-muted hover:text-j-cyan hover:border-j-cyan disabled:opacity-40 transition-colors font-mono"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* SMB share info banner */}
      <div className="flex items-start gap-2 px-3 py-2 rounded border border-j-border bg-j-surf text-j-muted text-xs font-mono">
        <Info size={13} className="text-j-cyan mt-0.5 shrink-0" />
        <span>
          Drop images into <span className="text-j-text">\\KJLC-AI-01\HolomatGallery</span> (SMB) or{' '}
          <span className="text-j-text">smb://KJLC-AI-01/HolomatGallery</span> — HEIC, PNG, JPG, WEBP supported.
          New items appear automatically via WebSocket.
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded border border-j-amber/30 bg-j-amber/5 text-j-amber text-xs font-mono">
          <AlertTriangle size={13} />
          {error}
        </div>
      )}

      {/* Grid */}
      {loading && items.length === 0 ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin text-j-cyan" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {items.map(item => (
            <GalleryCard
              key={item.id}
              item={item}
              meshyJob={meshyByItem[item.id]}
              onDelete={handleDelete}
              onSvgReady={svg => setSvgModal(svg)}
            />
          ))}
        </div>
      )}

      {/* SVG modal */}
      {svgModal && (
        <SvgModal svg={svgModal} onClose={() => setSvgModal(null)} />
      )}
    </div>
  )
}
