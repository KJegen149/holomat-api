/**
 * Meshy account browser — Phase 11 item 7.
 *
 * Lists every image-to-3D task on the connected Meshy account (independent of
 * Holomat's Gallery flow), with status filter chips, thumbnails, and a
 * one-click import for SUCCEEDED tasks.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  X, Loader2, AlertTriangle, Download, CheckCircle2, Sparkles, RefreshCw, ExternalLink,
} from 'lucide-react'
import {
  fetchMeshyTasks, importMeshyTask,
  type MeshyTask, type MeshyTaskStatus,
} from '../api/client'

const STATUS_FILTERS: { label: string; value: MeshyTaskStatus }[] = [
  { label: 'All',         value: ''            },
  { label: 'Completed',   value: 'SUCCEEDED'   },
  { label: 'In Progress', value: 'IN_PROGRESS' },
  { label: 'Failed',      value: 'FAILED'      },
]

const STATUS_COLOR: Record<string, string> = {
  PENDING:     'text-j-muted  border-j-border',
  IN_PROGRESS: 'text-j-amber  border-j-amber/40',
  SUCCEEDED:   'text-j-green  border-j-green/40',
  FAILED:      'text-j-red    border-j-red/40',
  CANCELED:    'text-j-cdim   border-j-border',
}

interface Props {
  open: boolean
  onClose: () => void
  onImported?: (filename: string) => void
}

export default function MeshyBrowseModal({ open, onClose, onImported }: Props) {
  const [filter, setFilter] = useState<MeshyTaskStatus>('SUCCEEDED')
  const [tasks, setTasks] = useState<MeshyTask[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [importingId, setImportingId] = useState<string | null>(null)
  const [justImported, setJustImported] = useState<Record<string, string>>({})

  const load = useCallback(async (status: MeshyTaskStatus) => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetchMeshyTasks(status, 1, 40)
      setTasks(r.tasks)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tasks')
      setTasks([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      setFilter('SUCCEEDED')
      setJustImported({})
      load('SUCCEEDED')
    }
  }, [open, load])

  function selectFilter(value: MeshyTaskStatus) {
    setFilter(value)
    load(value)
  }

  async function handleImport(task: MeshyTask) {
    setImportingId(task.id)
    setError(null)
    try {
      const r = await importMeshyTask(task.id)
      setJustImported(prev => ({ ...prev, [task.id]: r.filename }))
      onImported?.(r.filename)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
    } finally {
      setImportingId(null)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className="bg-j-surf border border-j-border rounded-sm w-[960px] max-w-[95vw] max-h-[90vh]
                   flex flex-col overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-j-border flex-shrink-0">
          <Sparkles size={14} className="text-j-amber" />
          <span className="text-j-cyan font-sans text-[11px] font-bold tracking-[0.2em] uppercase">
            Meshy Library
          </span>
          <a
            href="https://app.meshy.ai/"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 font-mono text-[9px] text-j-cyan/80 hover:text-j-cyan"
            title="Open Meshy app in a new tab"
          >
            <ExternalLink size={9} /> open meshy
          </a>
          <div className="flex-1" />
          <button onClick={() => load(filter)} className="text-j-muted hover:text-j-text transition-colors" title="Refresh">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={onClose} className="text-j-muted hover:text-j-text transition-colors">
            <X size={14} />
          </button>
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-1.5 px-4 py-2 border-b border-j-border flex-shrink-0">
          {STATUS_FILTERS.map(f => (
            <button
              key={f.label}
              onClick={() => selectFilter(f.value)}
              className={`px-2.5 py-1 border rounded-sm font-mono text-[9px] tracking-[0.1em] uppercase
                ${filter === f.value
                  ? 'border-j-cyan text-j-cyan bg-j-cyan/10'
                  : 'border-j-border text-j-muted hover:text-j-text'}`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-3 border border-j-red bg-j-red/5 rounded-sm p-2.5
                            font-mono text-[10px] text-j-red flex items-start gap-2">
              <AlertTriangle size={11} className="mt-0.5 flex-shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={22} className="animate-spin text-j-cyan" />
            </div>
          ) : tasks.length === 0 ? (
            <p className="text-j-cdim font-mono text-[10px] text-center py-16">
              No tasks for this filter.
            </p>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-3">
              {tasks.map(t => {
                const pulled = justImported[t.id] || t.imported_filename
                const importable = t.status === 'SUCCEEDED' && t.has_stl
                const statusCls = STATUS_COLOR[t.status] ?? 'text-j-cdim border-j-border'
                return (
                  <div key={t.id} className="bg-j-bg border border-j-border rounded-sm overflow-hidden flex flex-col">
                    <div className="aspect-square bg-black/30 flex items-center justify-center overflow-hidden">
                      {t.thumbnail_url ? (
                        <img src={t.thumbnail_url} alt={t.prompt || t.id} className="w-full h-full object-cover" />
                      ) : (
                        <Sparkles size={28} className="text-j-cdim" />
                      )}
                    </div>
                    <div className="p-2 space-y-1.5 flex-1 flex flex-col">
                      <div className="font-sans text-[10px] text-j-text line-clamp-2 min-h-[26px]" title={t.prompt}>
                        {t.prompt || `Task ${t.id.slice(0, 8)}`}
                      </div>
                      <span className={`inline-block self-start px-1.5 py-0.5 border rounded-sm
                                        font-mono text-[8px] tracking-[0.1em] uppercase ${statusCls}`}>
                        {t.status}{t.status === 'IN_PROGRESS' && t.progress ? ` ${t.progress}%` : ''}
                      </span>
                      {pulled ? (
                        <div className="flex items-center gap-1 font-mono text-[9px] text-j-green truncate mt-auto" title={pulled}>
                          <CheckCircle2 size={10} /> {pulled}
                        </div>
                      ) : (
                        <button
                          onClick={() => handleImport(t)}
                          disabled={!importable || !!importingId}
                          title={importable ? 'Import STL to pool' : 'Only SUCCEEDED tasks with STL output can be imported'}
                          className="mt-auto flex items-center justify-center gap-1 py-1 border border-j-border text-j-muted
                                     hover:text-j-cyan hover:border-j-cyan disabled:opacity-40
                                     disabled:cursor-not-allowed transition-colors rounded-sm
                                     font-mono text-[9px] tracking-[0.05em] uppercase"
                        >
                          {importingId === t.id ? <Loader2 size={9} className="animate-spin" /> : <Download size={9} />}
                          Import
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
