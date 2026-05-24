/**
 * Thingiverse search & import modal — Phase 11 item 4.
 *
 * Two-step flow:
 *   1. Type a query → grid of Things (thumbnail / name / creator)
 *   2. Click a Thing → list of its files (STL-first); click [IMPORT] on any
 *      file to download it into scan_data/stls/ with a Thingiverse sidecar.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  Search, X, Loader2, AlertTriangle, ChevronLeft, Download, FileBox, CheckCircle2, ExternalLink,
} from 'lucide-react'
import {
  thingiverseSearch, thingiverseFiles, thingiverseImport,
  type ThingiverseThing, type ThingiverseFile,
} from '../api/client'

function fmtSize(bytes: number | null): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

interface Props {
  open: boolean
  onClose: () => void
  /** Called after a successful import so the parent can refresh its STL grid. */
  onImported?: (filename: string) => void
}

export default function ThingiverseSearchModal({ open, onClose, onImported }: Props) {
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [things, setThings] = useState<ThingiverseThing[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selected, setSelected] = useState<ThingiverseThing | null>(null)
  const [files, setFiles] = useState<ThingiverseFile[]>([])
  const [filesLoading, setFilesLoading] = useState(false)
  const [importingFileId, setImportingFileId] = useState<number | null>(null)
  const [imported, setImported] = useState<Record<number, string>>({})

  // Reset state every time the modal opens
  useEffect(() => {
    if (!open) return
    setQuery('')
    setSubmitted('')
    setThings([])
    setError(null)
    setSelected(null)
    setFiles([])
    setImported({})
  }, [open])

  const runSearch = useCallback(async (q: string) => {
    setSearching(true)
    setError(null)
    setSubmitted(q)
    try {
      const r = await thingiverseSearch(q, 1, 24)
      setThings(r.things)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed')
      setThings([])
    } finally {
      setSearching(false)
    }
  }, [])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const q = query.trim()
    if (q) runSearch(q)
  }

  async function openThing(t: ThingiverseThing) {
    setSelected(t)
    setFilesLoading(true)
    setError(null)
    setFiles([])
    try {
      const r = await thingiverseFiles(t.id)
      setFiles(r.files)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load files')
    } finally {
      setFilesLoading(false)
    }
  }

  async function importFile(f: ThingiverseFile) {
    if (!selected) return
    setImportingFileId(f.id)
    setError(null)
    try {
      const r = await thingiverseImport({
        thing_id: selected.id,
        file_id: f.id,
        thing_name: selected.name,
        file_name: f.name,
        thing_url: selected.public_url,
        creator: selected.creator,
        thumbnail_url: selected.thumbnail_url ?? undefined,
      })
      setImported(prev => ({ ...prev, [f.id]: r.filename }))
      onImported?.(r.filename)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
    } finally {
      setImportingFileId(null)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className="bg-j-surf border border-j-border rounded-sm w-[900px] max-w-[95vw] max-h-[90vh]
                   flex flex-col overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-j-border flex-shrink-0">
          {selected && (
            <button
              onClick={() => { setSelected(null); setFiles([]) }}
              className="text-j-muted hover:text-j-text transition-colors"
              title="Back to results"
            >
              <ChevronLeft size={14} />
            </button>
          )}
          <span className="text-j-cyan font-sans text-[11px] font-bold tracking-[0.2em] uppercase">
            {selected ? selected.name : 'Thingiverse Search'}
          </span>
          {selected && (
            <a
              href={selected.public_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 font-mono text-[9px] text-j-cyan/80 hover:text-j-cyan"
            >
              <ExternalLink size={9} /> view
            </a>
          )}
          <div className="flex-1" />
          <button onClick={onClose} className="text-j-muted hover:text-j-text transition-colors">
            <X size={14} />
          </button>
        </div>

        {/* Search bar (hidden while drilled into a Thing) */}
        {!selected && (
          <form onSubmit={handleSubmit} className="flex items-center gap-2 px-4 py-3 border-b border-j-border flex-shrink-0">
            <Search size={12} className="text-j-muted" />
            <input
              type="text"
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search Thingiverse…"
              className="flex-1 bg-j-bg border border-j-border text-j-text font-mono text-[11px]
                         rounded-sm px-2 py-1.5 focus:outline-none focus:border-j-cyan
                         placeholder:text-j-cdim"
            />
            <button
              type="submit"
              disabled={!query.trim() || searching}
              className="px-3 py-1.5 bg-j-cyan/10 border border-j-cyan text-j-cyan
                         font-sans font-bold text-[10px] tracking-[0.2em] uppercase
                         hover:bg-j-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors rounded-sm"
            >
              {searching ? <Loader2 size={11} className="animate-spin" /> : 'Search'}
            </button>
          </form>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-3 border border-j-red bg-j-red/5 rounded-sm p-2.5
                            font-mono text-[10px] text-j-red flex items-start gap-2">
              <AlertTriangle size={11} className="mt-0.5 flex-shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          )}

          {/* Results grid */}
          {!selected && (
            <>
              {searching ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 size={22} className="animate-spin text-j-cyan" />
                </div>
              ) : things.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
                  <Search size={36} strokeWidth={1} className="text-j-cdim" />
                  <p className="text-j-cdim text-xs font-mono">
                    {submitted ? `No results for "${submitted}"` : 'Type a query and press Search'}
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-3">
                  {things.map(t => (
                    <button
                      key={t.id}
                      onClick={() => openThing(t)}
                      className="bg-j-bg border border-j-border rounded-sm overflow-hidden text-left
                                 hover:border-j-cyan transition-colors group"
                    >
                      <div className="aspect-square bg-black/30 flex items-center justify-center overflow-hidden">
                        {t.thumbnail_url ? (
                          <img src={t.thumbnail_url} alt={t.name} className="w-full h-full object-cover" />
                        ) : (
                          <FileBox size={28} className="text-j-cdim" />
                        )}
                      </div>
                      <div className="p-2 space-y-0.5">
                        <div className="font-sans text-[10px] text-j-text truncate" title={t.name}>
                          {t.name}
                        </div>
                        <div className="font-mono text-[9px] text-j-muted truncate">
                          {t.creator}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Files for selected Thing */}
          {selected && (
            <div className="space-y-2">
              {filesLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={18} className="animate-spin text-j-cyan" />
                </div>
              ) : files.length === 0 ? (
                <p className="text-j-cdim font-mono text-[10px] text-center py-8">
                  This Thing has no downloadable files.
                </p>
              ) : files.map(f => {
                const importedAs = imported[f.id]
                const isImporting = importingFileId === f.id
                return (
                  <div
                    key={f.id}
                    className={`flex items-center gap-2 p-2.5 border rounded-sm
                      ${f.is_stl ? 'border-j-border' : 'border-j-border opacity-60'}`}
                  >
                    <FileBox size={12} className={f.is_stl ? 'text-j-cyan' : 'text-j-muted'} />
                    <div className="flex-1 min-w-0">
                      <div className="font-sans text-[11px] text-j-text truncate">{f.name}</div>
                      <div className="font-mono text-[9px] text-j-muted">
                        {fmtSize(f.size)}{f.is_stl ? '' : ' · non-STL'}
                      </div>
                    </div>
                    {importedAs ? (
                      <span className="flex items-center gap-1 font-mono text-[10px] text-j-green">
                        <CheckCircle2 size={11} /> Imported
                      </span>
                    ) : (
                      <button
                        onClick={() => importFile(f)}
                        disabled={!f.is_stl || isImporting || !!importingFileId}
                        title={f.is_stl ? 'Import to STL pool' : 'Only STL files can be imported'}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 border border-j-border text-j-muted
                                   hover:text-j-cyan hover:border-j-cyan disabled:opacity-40
                                   disabled:cursor-not-allowed transition-colors rounded-sm
                                   font-mono text-[10px] tracking-[0.05em] uppercase"
                      >
                        {isImporting ? <Loader2 size={10} className="animate-spin" /> : <Download size={10} />}
                        Import
                      </button>
                    )}
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
