/**
 * MakerWorld paste-URL import — Phase 11 item 5.
 *
 * No public search API exists, so this is a paste-URL flow: drop a
 * makerworld.com link in → backend resolves the design via reverse-engineered
 * Bambu Cloud endpoints → confirm preview → import downloads the 3MF into
 * the pool.
 */
import { useState } from 'react'
import {
  X, Loader2, AlertTriangle, Download, ExternalLink, ClipboardPaste, CheckCircle2, Globe,
} from 'lucide-react'
import {
  makerworldResolve, makerworldImport,
  type MakerWorldDesign,
} from '../api/client'

interface Props {
  open: boolean
  onClose: () => void
  onImported?: (filename: string) => void
}

export default function MakerWorldPasteModal({ open, onClose, onImported }: Props) {
  const [url, setUrl] = useState('')
  const [resolving, setResolving] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [design, setDesign] = useState<MakerWorldDesign | null>(null)
  const [importedFilename, setImportedFilename] = useState<string | null>(null)

  async function handlePaste() {
    try {
      const txt = await navigator.clipboard.readText()
      if (txt) setUrl(txt.trim())
    } catch { /* clipboard may be denied — leave manual */ }
  }

  async function handleResolve(e?: React.FormEvent) {
    e?.preventDefault()
    if (!url.trim()) return
    setResolving(true)
    setError(null)
    setDesign(null)
    setImportedFilename(null)
    try {
      const d = await makerworldResolve(url.trim())
      setDesign(d)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Resolve failed')
    } finally {
      setResolving(false)
    }
  }

  async function handleImport() {
    if (!design) return
    setImporting(true)
    setError(null)
    try {
      const r = await makerworldImport(url.trim())
      setImportedFilename(r.filename)
      onImported?.(r.filename)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  function handleReset() {
    setUrl('')
    setDesign(null)
    setError(null)
    setImportedFilename(null)
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className="bg-j-surf border border-j-border rounded-sm w-[560px] max-w-[95vw]
                   flex flex-col overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-j-border flex-shrink-0">
          <Globe size={14} className="text-j-cyan" />
          <span className="text-j-cyan font-sans text-[11px] font-bold tracking-[0.2em] uppercase">
            MakerWorld Import
          </span>
          <div className="flex-1" />
          <button onClick={onClose} className="text-j-muted hover:text-j-text transition-colors">
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-3">
          <p className="font-mono text-[10px] text-j-cdim leading-relaxed">
            Paste a makerworld.com model URL. The 3MF is downloaded into the pool
            as-is — OrcaSlicer re-slices it with the Holomat P1S profile at print
            time.
          </p>

          <form onSubmit={handleResolve} className="flex gap-2">
            <input
              type="text"
              autoFocus
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://makerworld.com/en/models/12345"
              className="flex-1 bg-j-bg border border-j-border text-j-text font-mono text-[11px]
                         rounded-sm px-2 py-1.5 focus:outline-none focus:border-j-cyan
                         placeholder:text-j-cdim"
            />
            <button
              type="button"
              onClick={handlePaste}
              title="Paste from clipboard"
              className="px-2 py-1.5 border border-j-border text-j-muted hover:text-j-text hover:border-j-text
                         transition-colors rounded-sm"
            >
              <ClipboardPaste size={11} />
            </button>
            <button
              type="submit"
              disabled={!url.trim() || resolving}
              className="px-3 py-1.5 bg-j-cyan/10 border border-j-cyan text-j-cyan
                         font-sans font-bold text-[10px] tracking-[0.2em] uppercase
                         hover:bg-j-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors rounded-sm"
            >
              {resolving ? <Loader2 size={11} className="animate-spin" /> : 'Resolve'}
            </button>
          </form>

          {error && (
            <div className="border border-j-red bg-j-red/5 rounded-sm p-2.5
                            font-mono text-[10px] text-j-red flex items-start gap-2">
              <AlertTriangle size={11} className="mt-0.5 flex-shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          )}

          {design && (
            <div className="border border-j-border rounded-sm p-3 flex gap-3">
              <div className="w-20 h-20 bg-black/30 rounded-sm flex items-center justify-center overflow-hidden flex-shrink-0">
                {design.thumbnail_url ? (
                  <img src={design.thumbnail_url} alt={design.name} className="w-full h-full object-cover" />
                ) : (
                  <Globe size={24} className="text-j-cdim" />
                )}
              </div>
              <div className="flex-1 min-w-0 space-y-1">
                <div className="font-sans text-[12px] text-j-text truncate" title={design.name}>
                  {design.name}
                </div>
                <div className="font-mono text-[10px] text-j-muted">by {design.creator}</div>
                <a
                  href={design.public_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 font-mono text-[9px] text-j-cyan/80 hover:text-j-cyan"
                >
                  <ExternalLink size={9} /> view on MakerWorld
                </a>
                {importedFilename ? (
                  <div className="flex items-center gap-1 font-mono text-[10px] text-j-green">
                    <CheckCircle2 size={11} /> Imported as {importedFilename}
                  </div>
                ) : (
                  <div className="flex gap-1.5 pt-1">
                    <button
                      onClick={handleImport}
                      disabled={importing}
                      className="flex items-center gap-1.5 px-2.5 py-1 border border-j-border text-j-muted
                                 hover:text-j-cyan hover:border-j-cyan disabled:opacity-40
                                 transition-colors rounded-sm font-mono text-[10px] uppercase"
                    >
                      {importing ? <Loader2 size={10} className="animate-spin" /> : <Download size={10} />}
                      Import 3MF
                    </button>
                    <button
                      onClick={handleReset}
                      disabled={importing}
                      className="px-2.5 py-1 border border-j-border text-j-muted hover:text-j-text
                                 disabled:opacity-40 transition-colors rounded-sm font-mono text-[10px] uppercase"
                    >
                      Clear
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
