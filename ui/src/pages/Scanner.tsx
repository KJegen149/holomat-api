import { useState } from 'react'
import {
  Camera, Scan, RefreshCw, Pin, PinOff, Trash2, Box,
  CheckCircle, AlertTriangle, Package,
} from 'lucide-react'
import { useScanner, type ScanObject } from '../hooks/useScanner'
import { generateCase } from '../api/client'

// ── Confidence badge ────────────────────────────────────────────────────────

function ConfidencePill({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const cls =
    pct >= 80 ? 'text-j-green border-j-green bg-j-green/5' :
    pct >= 50 ? 'text-j-amber border-j-amber bg-j-amber/5' :
                'text-j-muted border-j-border bg-transparent'
  return (
    <span className={`border rounded-sm px-1.5 py-0.5 font-mono text-[9px] tracking-[0.1em] ${cls}`}>
      {pct}%
    </span>
  )
}

// ── Last scan result panel ──────────────────────────────────────────────────

function ScanResult({
  result,
  onUpdateHeight,
  onDelete,
  onPin,
}: {
  result: ScanObject
  onUpdateHeight: (id: string, h: number) => void
  onDelete: (id: string) => void
  onPin: (id: string, pinned: boolean) => void
}) {
  const [heightInput, setHeightInput] = useState(
    result.height_mm != null ? String(result.height_mm) : ''
  )
  const [generating, setGenerating]   = useState(false)
  const [caseCode, setCaseCode]       = useState<string | null>(null)
  const [caseErr, setCaseErr]         = useState<string | null>(null)

  function handleHeightBlur() {
    const v = parseFloat(heightInput)
    if (!isNaN(v) && v >= 0) onUpdateHeight(result.id, v)
  }

  async function handleGenerateCase() {
    setGenerating(true)
    setCaseErr(null)
    setCaseCode(null)
    try {
      const r = await generateCase(result.id)
      setCaseCode(r.code)
    } catch (e) {
      setCaseErr(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="border border-j-cyan bg-j-cyan/5 rounded-sm p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <CheckCircle size={13} className="text-j-cyan flex-shrink-0 mt-0.5" />
          <span className="text-j-cyan font-mono text-[11px] tracking-[0.1em] uppercase font-semibold">
            Scan Complete
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onPin(result.id, !result.pinned)}
            title={result.pinned ? 'Unpin' : 'Pin'}
            className="p-1 text-j-muted hover:text-j-cyan transition-colors"
          >
            {result.pinned ? <Pin size={13} /> : <PinOff size={13} />}
          </button>
          <button
            onClick={() => onDelete(result.id)}
            disabled={result.pinned}
            title="Delete"
            className="p-1 text-j-muted hover:text-j-red disabled:opacity-30 transition-colors"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Thumbnail + identity */}
      <div className="flex gap-3">
        {result.thumbnail_b64 ? (
          <img
            src={`data:image/jpeg;base64,${result.thumbnail_b64}`}
            alt={result.name}
            className="w-16 h-16 object-cover rounded-sm border border-j-border flex-shrink-0 bg-black"
          />
        ) : (
          <div className="w-16 h-16 rounded-sm border border-j-border flex items-center justify-center bg-black flex-shrink-0">
            <Package size={24} strokeWidth={1} className="text-j-muted" />
          </div>
        )}
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-sans font-semibold text-[12px] text-j-text truncate">
              {result.name}
            </span>
            <ConfidencePill value={result.confidence} />
          </div>
          {result.brand && (
            <div className="font-mono text-[10px] text-j-muted truncate">
              {result.brand}{result.model ? ` — ${result.model}` : ''}
            </div>
          )}
          <div className="font-mono text-[9px] text-j-cdim uppercase tracking-[0.1em]">
            {result.category}
          </div>
        </div>
      </div>

      {/* Dimensions */}
      <div className="border border-j-border rounded-sm p-2.5 grid grid-cols-3 gap-2">
        {[
          ['W', result.width_mm.toFixed(1)],
          ['D', result.depth_mm.toFixed(1)],
        ].map(([label, val]) => (
          <div key={label} className="text-center">
            <div className="font-mono text-[9px] text-j-muted tracking-[0.15em] uppercase">{label}</div>
            <div className="font-mono text-[12px] text-j-text font-semibold">{val}</div>
            <div className="font-mono text-[8px] text-j-cdim">mm</div>
          </div>
        ))}
        {/* Height: user-editable */}
        <div className="text-center">
          <div className="font-mono text-[9px] text-j-muted tracking-[0.15em] uppercase">H</div>
          <input
            type="number"
            min={0}
            step={0.1}
            value={heightInput}
            onChange={e => setHeightInput(e.target.value)}
            onBlur={handleHeightBlur}
            placeholder="—"
            className="w-full text-center font-mono text-[12px] text-j-text font-semibold
                       bg-transparent border-b border-j-border focus:border-j-cyan outline-none
                       placeholder:text-j-cdim"
          />
          <div className="font-mono text-[8px] text-j-cdim">mm</div>
        </div>
      </div>

      {/* Generate case button */}
      <button
        onClick={handleGenerateCase}
        disabled={generating}
        className="w-full py-2 bg-j-border/30 border border-j-border text-j-muted
                   font-sans font-semibold text-[11px] tracking-[0.15em] uppercase
                   hover:border-j-cyan hover:text-j-cyan disabled:opacity-40
                   disabled:cursor-not-allowed transition-colors rounded-sm flex items-center justify-center gap-2"
      >
        {generating
          ? <><RefreshCw size={11} className="animate-spin" /> Generating...</>
          : <><Box size={11} /> Generate Case</>}
      </button>

      {caseErr && (
        <div className="font-mono text-[10px] text-j-red break-words">{caseErr}</div>
      )}

      {caseCode && (
        <div className="space-y-1">
          <div className="font-mono text-[9px] text-j-muted uppercase tracking-[0.1em]">
            OpenSCAD — copy to OrcaSlicer
          </div>
          <pre className="bg-black border border-j-border rounded-sm p-2 font-mono text-[9px]
                          text-j-text overflow-auto max-h-40 whitespace-pre-wrap">
            {caseCode}
          </pre>
        </div>
      )}
    </div>
  )
}

// ── Library card ────────────────────────────────────────────────────────────

function LibraryCard({
  item,
  onPin,
  onDelete,
}: {
  item: Omit<ScanObject, 'thumbnail_b64'>
  onPin: (id: string, pinned: boolean) => void
  onDelete: (id: string) => void
}) {
  const [deleteConfirm, setDeleteConfirm] = useState(false)

  return (
    <div className="border border-j-border rounded-sm p-2.5 space-y-1.5 relative group">
      {item.pinned && (
        <div className="absolute top-1.5 right-1.5">
          <Pin size={9} className="text-j-cyan" />
        </div>
      )}
      <div className="font-sans text-[11px] text-j-text font-semibold truncate pr-4">
        {item.name}
      </div>
      {item.brand && (
        <div className="font-mono text-[9px] text-j-muted truncate">{item.brand}</div>
      )}
      <div className="font-mono text-[9px] text-j-cdim uppercase tracking-[0.1em]">
        {item.category}
      </div>
      <div className="font-mono text-[10px] text-j-text">
        {item.width_mm.toFixed(0)}×{item.depth_mm.toFixed(0)}
        {item.height_mm != null ? `×${item.height_mm.toFixed(0)}` : ''} mm
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onPin(item.id, !item.pinned)}
          className="p-0.5 text-j-muted hover:text-j-cyan transition-colors"
          title={item.pinned ? 'Unpin' : 'Pin'}
        >
          {item.pinned ? <PinOff size={10} /> : <Pin size={10} />}
        </button>
        {!item.pinned && (
          <button
            onClick={() => {
              if (!deleteConfirm) { setDeleteConfirm(true); return }
              onDelete(item.id)
            }}
            onBlur={() => setDeleteConfirm(false)}
            className={`p-0.5 transition-colors text-[9px] font-mono ${
              deleteConfirm ? 'text-j-red' : 'text-j-muted hover:text-j-red'
            }`}
            title="Delete"
          >
            {deleteConfirm ? '!' : <Trash2 size={10} />}
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────────────────

export default function Scanner() {
  const {
    bgStatus, bgCapturing, captureBackgroundFrame,
    scanning, lastScan, scan,
    library, refreshLibrary,
    togglePin, updateHeight, deleteItem,
    error, clearError,
  } = useScanner()

  const [showPreview, setShowPreview] = useState(true)

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: camera preview */}
      <div className="flex-1 flex flex-col overflow-hidden border-r border-j-border">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-j-border bg-j-surf flex-shrink-0">
          <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
            CAMERA // <span className="text-j-muted font-normal">SCAN PREVIEW</span>
          </span>
          <button
            onClick={() => setShowPreview(v => !v)}
            className="text-[10px] tracking-[0.15em] text-j-muted hover:text-j-text uppercase font-sans transition-colors"
          >
            {showPreview ? 'HIDE' : 'SHOW'}
          </button>
        </div>

        <div className="flex-1 flex items-center justify-center bg-black overflow-hidden">
          {showPreview ? (
            <img
              src="/api/camera/stream"
              alt="Camera feed"
              className="max-w-full max-h-full object-contain"
            />
          ) : (
            <div className="flex flex-col items-center gap-3 text-j-muted">
              <Camera size={40} strokeWidth={1} />
              <span className="font-mono text-[11px] tracking-[0.15em] uppercase">Preview hidden</span>
            </div>
          )}
        </div>

        {/* Background status bar */}
        <div className={`px-4 py-2 flex items-center gap-2 border-t border-j-border flex-shrink-0 ${
          bgStatus.captured ? 'bg-j-green/5' : 'bg-j-amber/5'
        }`}>
          {bgStatus.captured
            ? <CheckCircle size={11} className="text-j-green flex-shrink-0" />
            : <AlertTriangle size={11} className="text-j-amber flex-shrink-0" />}
          <span className={`font-mono text-[10px] ${bgStatus.captured ? 'text-j-green' : 'text-j-amber'}`}>
            {bgStatus.captured
              ? `Background set — ${bgStatus.captured_at ? new Date(bgStatus.captured_at).toLocaleTimeString() : ''}`
              : 'No background — capture empty mat first'}
          </span>
        </div>
      </div>

      {/* Right: controls + results + library */}
      <div className="w-[320px] flex flex-col bg-j-surf flex-shrink-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-j-border flex-shrink-0">
          <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
            SCANNER // <span className="text-j-muted font-normal">PHASE 4</span>
          </span>
        </div>

        <div className="flex-1 p-4 space-y-4 overflow-y-auto">
          {/* Error */}
          {error && (
            <div className="border border-j-red bg-j-red/5 rounded-sm p-3 flex items-start justify-between gap-2">
              <div className="text-j-red font-mono text-[10px] break-words">{error}</div>
              <button onClick={clearError} className="text-j-red/60 hover:text-j-red text-[10px] flex-shrink-0">✕</button>
            </div>
          )}

          {/* Instructions */}
          {!bgStatus.captured && (
            <section>
              <h3 className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase mb-2">
                Setup
              </h3>
              <ol className="space-y-1.5">
                {[
                  'Clear the mat — remove all objects',
                  'Click CAPTURE BACKGROUND below',
                  'Place object flat on the mat',
                  'Click SCAN OBJECT',
                ].map((step, i) => (
                  <li key={i} className="flex gap-2 font-mono text-[10px] text-j-muted">
                    <span className="text-j-cdim flex-shrink-0">{i + 1}.</span>
                    {step}
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Last scan result */}
          {lastScan && (
            <section>
              <h3 className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase mb-2">
                Last Scan
              </h3>
              <ScanResult
                result={lastScan}
                onUpdateHeight={updateHeight}
                onDelete={deleteItem}
                onPin={togglePin}
              />
            </section>
          )}

          {/* Library */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase">
                Library <span className="text-j-cdim">({library.length}/50)</span>
              </h3>
              <button
                onClick={refreshLibrary}
                className="text-j-muted hover:text-j-text transition-colors"
                title="Refresh library"
              >
                <RefreshCw size={10} />
              </button>
            </div>

            {library.length === 0 ? (
              <div className="border border-j-border rounded-sm p-4 text-center">
                <Scan size={24} strokeWidth={1} className="text-j-muted mx-auto mb-2" />
                <div className="font-mono text-[10px] text-j-muted">No objects scanned yet</div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {library.map(item => (
                  <LibraryCard
                    key={item.id}
                    item={item}
                    onPin={togglePin}
                    onDelete={deleteItem}
                  />
                ))}
              </div>
            )}
          </section>
        </div>

        {/* Action buttons */}
        <div className="p-4 border-t border-j-border space-y-2 flex-shrink-0">
          <button
            onClick={captureBackgroundFrame}
            disabled={bgCapturing}
            className="w-full py-2.5 bg-j-amber/10 border border-j-amber text-j-amber
                       font-sans font-bold text-[12px] tracking-[0.2em] uppercase
                       hover:bg-j-amber/20 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors duration-150 rounded-sm"
          >
            {bgCapturing
              ? <span className="flex items-center justify-center gap-2">
                  <RefreshCw size={12} className="animate-spin" /> CAPTURING BG...
                </span>
              : 'CAPTURE BACKGROUND'}
          </button>

          <button
            onClick={scan}
            disabled={scanning || !bgStatus.captured}
            className="w-full py-2.5 bg-j-cyan/10 border border-j-cyan text-j-cyan
                       font-sans font-bold text-[12px] tracking-[0.2em] uppercase
                       hover:bg-j-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors duration-150 rounded-sm"
          >
            {scanning
              ? <span className="flex items-center justify-center gap-2">
                  <RefreshCw size={12} className="animate-spin" /> SCANNING...
                </span>
              : 'SCAN OBJECT'}
          </button>
        </div>
      </div>
    </div>
  )
}
