import { useState } from 'react'
import {
  Printer, RefreshCw, X, CheckCircle, AlertTriangle,
  Clock, Layers, Loader, Ban, ChevronDown, ChevronUp, Plus, Trash2,
} from 'lucide-react'
import { usePrint, type PrintJob, type PrintProfile } from '../hooks/usePrint'

// ── State badge ──────────────────────────────────────────────────────────────

function StateBadge({ state }: { state: PrintJob['state'] }) {
  const cfg: Record<PrintJob['state'], { label: string; cls: string; Icon: typeof Clock }> = {
    queued:    { label: 'QUEUED',    cls: 'text-j-muted  border-j-muted',  Icon: Clock   },
    slicing:   { label: 'SLICING',   cls: 'text-j-amber  border-j-amber',  Icon: Loader  },
    uploading: { label: 'UPLOADING', cls: 'text-j-amber  border-j-amber',  Icon: Loader  },
    printing:  { label: 'PRINTING',  cls: 'text-j-cyan   border-j-cyan',   Icon: Printer },
    done:      { label: 'DONE',      cls: 'text-j-green  border-j-green',  Icon: CheckCircle },
    failed:    { label: 'FAILED',    cls: 'text-j-red    border-j-red',    Icon: AlertTriangle },
    cancelled: { label: 'CANCELLED', cls: 'text-j-cdim   border-j-cdim',   Icon: Ban     },
  }
  const { label, cls, Icon } = cfg[state] ?? cfg.queued
  const spin = state === 'slicing' || state === 'uploading'
  return (
    <span className={`inline-flex items-center gap-1 border rounded-sm px-1.5 py-0.5
                      font-mono text-[9px] tracking-[0.1em] ${cls}`}>
      <Icon size={9} className={spin ? 'animate-spin' : ''} />
      {label}
    </span>
  )
}

// ── Job row ──────────────────────────────────────────────────────────────────

function JobRow({ job, onCancel }: { job: PrintJob; onCancel: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false)
  const isPrinting = job.state === 'printing'

  return (
    <div className="border border-j-border rounded-sm overflow-hidden">
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-j-border/20 transition-colors"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-sans text-[11px] text-j-text font-semibold truncate">{job.name}</span>
            <StateBadge state={job.state} />
          </div>
          {isPrinting && (
            <div className="mt-1 h-1 bg-j-border rounded-full overflow-hidden">
              <div
                className="h-full bg-j-cyan transition-all duration-500"
                style={{ width: `${job.progress}%` }}
              />
            </div>
          )}
        </div>
        {isPrinting && (
          <span className="font-mono text-[10px] text-j-cyan flex-shrink-0">{job.progress}%</span>
        )}
        {job.state === 'queued' && (
          <button
            onClick={e => { e.stopPropagation(); onCancel(job.id) }}
            title="Cancel job"
            className="p-1 text-j-muted hover:text-j-red transition-colors flex-shrink-0"
          >
            <X size={11} />
          </button>
        )}
        {expanded ? <ChevronUp size={11} className="text-j-muted flex-shrink-0" /> : <ChevronDown size={11} className="text-j-muted flex-shrink-0" />}
      </div>

      {expanded && (
        <div className="border-t border-j-border bg-j-bg px-3 py-2 space-y-1">
          {[
            ['Profile', job.profile_id],
            ['STL', job.stl_path.split('/').pop() ?? job.stl_path],
            ['Created', new Date(job.created_at).toLocaleString()],
            job.started_at    ? ['Started', new Date(job.started_at).toLocaleString()]    : null,
            job.completed_at  ? ['Completed', new Date(job.completed_at).toLocaleString()] : null,
          ].filter(Boolean).map((row) => { const [k, v] = row as [string, string]; return (
            <div key={k} className="flex gap-2 font-mono text-[9px]">
              <span className="text-j-cdim w-20 flex-shrink-0">{k}</span>
              <span className="text-j-muted break-all">{v}</span>
            </div>
          ); })}
          {job.error && (
            <div className="mt-1 text-j-red font-mono text-[9px] break-all">{job.error}</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Printer status panel ─────────────────────────────────────────────────────

function PrinterStatusPanel({ status }: { status: ReturnType<typeof usePrint>['status'] }) {
  if (!status) {
    return (
      <div className="border border-j-border rounded-sm p-3 flex items-center gap-2 text-j-muted">
        <Printer size={13} strokeWidth={1.5} />
        <span className="font-mono text-[10px]">Connecting to printer...</span>
      </div>
    )
  }
  if (status.error) {
    return (
      <div className="border border-j-border rounded-sm p-3 flex items-start gap-2">
        <AlertTriangle size={13} className="text-j-amber flex-shrink-0 mt-0.5" />
        <span className="font-mono text-[10px] text-j-amber break-words">{status.error}</span>
      </div>
    )
  }

  const stateStr = (status.state ?? 'UNKNOWN').toUpperCase()
  const isPrinting = stateStr === 'PRINTING' || stateStr === 'RUNNING'
  const stateColor = isPrinting ? 'text-j-cyan' : stateStr === 'IDLE' ? 'text-j-green' : 'text-j-muted'

  return (
    <div className="border border-j-border rounded-sm p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Printer size={13} strokeWidth={1.5} className={stateColor} />
        <span className={`font-mono text-[10px] font-semibold tracking-[0.1em] ${stateColor}`}>
          {stateStr}
        </span>
        {status.current_file && (
          <span className="font-mono text-[9px] text-j-muted truncate ml-auto max-w-[120px]">
            {status.current_file}
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[
          ['Nozzle', `${status.nozzle_temp?.toFixed(0) ?? '—'}°C`],
          ['Bed',    `${status.bed_temp?.toFixed(0)    ?? '—'}°C`],
          ['Progress', `${status.progress ?? 0}%`],
        ].map(([label, val]) => (
          <div key={label} className="text-center">
            <div className="font-mono text-[8px] text-j-cdim uppercase tracking-[0.1em]">{label}</div>
            <div className="font-mono text-[11px] text-j-text font-semibold">{val}</div>
          </div>
        ))}
      </div>
      {isPrinting && (
        <div className="h-1 bg-j-border rounded-full overflow-hidden">
          <div
            className="h-full bg-j-cyan transition-all"
            style={{ width: `${status.progress ?? 0}%` }}
          />
        </div>
      )}
    </div>
  )
}

// ── Add-to-queue form ────────────────────────────────────────────────────────

function AddJobForm({
  stls,
  profiles,
  loading,
  onAdd,
}: {
  stls: ReturnType<typeof usePrint>['stls']
  profiles: PrintProfile[]
  loading: boolean
  onAdd: (stl: string, profile: string, name: string) => void
}) {
  const [selectedStl,     setSelectedStl]     = useState('')
  const [selectedProfile, setSelectedProfile] = useState('standard')
  const [jobName,         setJobName]         = useState('')

  const selectCls = `w-full bg-j-bg border border-j-border text-j-text font-mono text-[10px]
                     rounded-sm px-2 py-1.5 focus:outline-none focus:border-j-cyan`

  function handleAdd() {
    if (!selectedStl) return
    onAdd(selectedStl, selectedProfile, jobName.trim())
    setJobName('')
  }

  return (
    <div className="space-y-2">
      <div>
        <label className="block font-mono text-[9px] text-j-muted tracking-[0.1em] uppercase mb-1">
          STL File
        </label>
        <select className={selectCls} value={selectedStl} onChange={e => setSelectedStl(e.target.value)}>
          <option value="">— select STL —</option>
          {stls.map(s => (
            <option key={s.filename} value={s.filename}>{s.stem}</option>
          ))}
        </select>
        {stls.length === 0 && (
          <div className="font-mono text-[9px] text-j-cdim mt-1">
            No STL files found — compile a model in the Scanner tab first.
          </div>
        )}
      </div>

      <div>
        <label className="block font-mono text-[9px] text-j-muted tracking-[0.1em] uppercase mb-1">
          Print Profile
        </label>
        <select className={selectCls} value={selectedProfile} onChange={e => setSelectedProfile(e.target.value)}>
          {profiles.map(p => (
            <option key={p.id} value={p.id}>
              {p.name} — {p.layer_height}mm / {p.infill_percent}% infill
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block font-mono text-[9px] text-j-muted tracking-[0.1em] uppercase mb-1">
          Job Name <span className="text-j-cdim">(optional)</span>
        </label>
        <input
          type="text"
          value={jobName}
          onChange={e => setJobName(e.target.value)}
          placeholder="defaults to filename"
          className={`${selectCls} placeholder:text-j-cdim`}
        />
      </div>

      <button
        onClick={handleAdd}
        disabled={!selectedStl || loading}
        className="w-full py-2 bg-j-cyan/10 border border-j-cyan text-j-cyan
                   font-sans font-bold text-[11px] tracking-[0.2em] uppercase
                   hover:bg-j-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed
                   transition-colors duration-150 rounded-sm flex items-center justify-center gap-2"
      >
        {loading
          ? <><RefreshCw size={11} className="animate-spin" /> Queuing...</>
          : <><Plus size={11} /> Add to Queue</>}
      </button>
    </div>
  )
}

// ── Profile manager ──────────────────────────────────────────────────────────

function ProfileManager({
  profiles,
  onAdd,
  onDelete,
}: {
  profiles: PrintProfile[]
  onAdd: (b: { name: string; layer_height: number; infill_percent: number; supports: string }) => void
  onDelete: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [name,    setName]    = useState('')
  const [lh,      setLh]      = useState('0.20')
  const [infill,  setInfill]  = useState('15')
  const [sup,     setSup]     = useState('none')

  function handleAdd() {
    if (!name.trim()) return
    onAdd({
      name: name.trim(),
      layer_height: parseFloat(lh) || 0.20,
      infill_percent: parseInt(infill) || 15,
      supports: sup,
    })
    setName('')
  }

  const inputCls = `bg-j-bg border border-j-border text-j-text font-mono text-[10px]
                    rounded-sm px-2 py-1.5 focus:outline-none focus:border-j-cyan w-full`

  return (
    <div className="border border-j-border rounded-sm overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-3 py-2
                   font-mono text-[10px] text-j-muted hover:text-j-text transition-colors"
        onClick={() => setOpen(v => !v)}
      >
        <span className="tracking-[0.1em] uppercase">Custom Profiles</span>
        {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
      </button>

      {open && (
        <div className="border-t border-j-border p-3 space-y-3">
          {/* Existing custom profiles */}
          {profiles.filter(p => !p.is_builtin).map(p => (
            <div key={p.id} className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-sans text-[11px] text-j-text">{p.name}</div>
                <div className="font-mono text-[9px] text-j-muted">
                  {p.layer_height}mm · {p.infill_percent}% · {p.supports}
                </div>
              </div>
              <button
                onClick={() => onDelete(p.id)}
                className="p-1 text-j-muted hover:text-j-red transition-colors flex-shrink-0"
                title="Delete profile"
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}

          {/* New profile form */}
          <div className="space-y-1.5 pt-1 border-t border-j-border">
            <div className="font-mono text-[9px] text-j-cdim uppercase tracking-[0.1em]">New Profile</div>
            <input
              type="text"
              placeholder="Profile name"
              value={name}
              onChange={e => setName(e.target.value)}
              className={`${inputCls} placeholder:text-j-cdim`}
            />
            <div className="grid grid-cols-3 gap-1.5">
              <div>
                <div className="font-mono text-[8px] text-j-cdim mb-0.5">Layer (mm)</div>
                <input type="number" min={0.05} max={0.35} step={0.01} value={lh}
                  onChange={e => setLh(e.target.value)} className={inputCls} />
              </div>
              <div>
                <div className="font-mono text-[8px] text-j-cdim mb-0.5">Infill %</div>
                <input type="number" min={5} max={100} value={infill}
                  onChange={e => setInfill(e.target.value)} className={inputCls} />
              </div>
              <div>
                <div className="font-mono text-[8px] text-j-cdim mb-0.5">Supports</div>
                <select value={sup} onChange={e => setSup(e.target.value)} className={inputCls}>
                  <option value="none">None</option>
                  <option value="normal">Normal</option>
                  <option value="tree">Tree</option>
                </select>
              </div>
            </div>
            <button
              onClick={handleAdd}
              disabled={!name.trim()}
              className="w-full py-1.5 bg-j-border/30 border border-j-border text-j-muted
                         font-sans text-[10px] tracking-[0.15em] uppercase
                         hover:border-j-cyan hover:text-j-cyan disabled:opacity-40
                         transition-colors rounded-sm flex items-center justify-center gap-1.5"
            >
              <Plus size={10} /> Add Profile
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Print() {
  const {
    status, stls, active, history, profiles,
    loading, error, clearError,
    refreshQueue, refreshStls,
    addJob, cancelJob, addProfile, removeProfile,
  } = usePrint()

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: queue + history */}
      <div className="flex-1 flex flex-col overflow-hidden border-r border-j-border">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-j-border bg-j-surf flex-shrink-0">
          <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
            PRINT QUEUE
          </span>
          <button
            onClick={refreshQueue}
            className="text-j-muted hover:text-j-text transition-colors"
            title="Refresh queue"
          >
            <RefreshCw size={11} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {error && (
            <div className="border border-j-red bg-j-red/5 rounded-sm p-3 flex items-start justify-between gap-2">
              <div className="text-j-red font-mono text-[10px] break-words">{error}</div>
              <button onClick={clearError} className="text-j-red/60 hover:text-j-red flex-shrink-0">
                <X size={11} />
              </button>
            </div>
          )}

          {/* Active jobs */}
          <section>
            <h3 className="font-mono text-[10px] text-j-muted tracking-[0.2em] uppercase mb-2">
              Active <span className="text-j-cdim">({active.length})</span>
            </h3>
            {active.length === 0 ? (
              <div className="border border-j-border rounded-sm p-4 flex flex-col items-center gap-2">
                <Layers size={28} strokeWidth={1} className="text-j-cdim" />
                <span className="font-mono text-[10px] text-j-cdim">Queue empty</span>
              </div>
            ) : (
              <div className="space-y-2">
                {active.map(job => (
                  <JobRow key={job.id} job={job} onCancel={cancelJob} />
                ))}
              </div>
            )}
          </section>

          {/* History */}
          {history.length > 0 && (
            <section>
              <h3 className="font-mono text-[10px] text-j-muted tracking-[0.2em] uppercase mb-2">
                History <span className="text-j-cdim">(last {history.length})</span>
              </h3>
              <div className="space-y-2">
                {[...history].reverse().map(job => (
                  <JobRow key={job.id} job={job} onCancel={cancelJob} />
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      {/* Right: controls */}
      <div className="w-[280px] flex flex-col bg-j-surf flex-shrink-0 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-j-border flex-shrink-0">
          <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
            CONTROLS
          </span>
        </div>

        <div className="flex-1 p-4 space-y-4 overflow-y-auto">
          {/* Printer status */}
          <section>
            <h3 className="font-mono text-[10px] text-j-muted tracking-[0.2em] uppercase mb-2">
              Bambu P1S
            </h3>
            <PrinterStatusPanel status={status} />
          </section>

          {/* Add to queue */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-mono text-[10px] text-j-muted tracking-[0.2em] uppercase">
                Add to Queue
              </h3>
              <button
                onClick={refreshStls}
                className="text-j-muted hover:text-j-text transition-colors"
                title="Refresh STL list"
              >
                <RefreshCw size={10} />
              </button>
            </div>
            <AddJobForm
              stls={stls}
              profiles={profiles}
              loading={loading}
              onAdd={addJob}
            />
          </section>

          {/* Profile manager */}
          <section>
            <ProfileManager
              profiles={profiles}
              onAdd={addProfile}
              onDelete={removeProfile}
            />
          </section>
        </div>
      </div>
    </div>
  )
}
