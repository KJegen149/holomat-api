import { useState } from 'react'
import { Camera, RefreshCw, CheckCircle, AlertTriangle } from 'lucide-react'
import { useCalibration } from '../hooks/useCalibration'

export default function Calibration() {
  const { status, capturing, computing, lastCapture, lastCompute, error, capture, compute, reset } =
    useCalibration()
  const [showPreview, setShowPreview]   = useState(true)
  const [resetConfirm, setResetConfirm] = useState(false)

  const MIN            = status?.min_captures_required ?? 12
  const sessionCaps    = status?.session_captures ?? 0
  const sessionReady   = status?.session_ready ?? false
  const progress       = Math.min(100, (sessionCaps / MIN) * 100)

  function handleReset() {
    if (!resetConfirm) { setResetConfirm(true); return }
    setResetConfirm(false)
    reset()
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: camera preview */}
      <div className="flex-1 flex flex-col overflow-hidden border-r border-j-border">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-j-border bg-j-surf flex-shrink-0">
          <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
            CAMERA // <span className="text-j-muted font-normal">LIVE PREVIEW</span>
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
      </div>

      {/* Right: controls */}
      <div className="w-[300px] flex flex-col bg-j-surf flex-shrink-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-j-border flex-shrink-0">
          <span className="text-[11px] font-bold tracking-[0.2em] text-j-cyan uppercase font-sans">
            CALIBRATION // <span className="text-j-muted font-normal">WIZARD</span>
          </span>
        </div>

        <div className="flex-1 p-5 space-y-5 overflow-y-auto">
          {/* Current calibration status */}
          <section>
            <h3 className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase mb-3">
              Current Status
            </h3>
            <div className={`border rounded-sm p-3 ${
              status?.valid
                ? 'border-j-green bg-j-green/5'
                : 'border-j-amber bg-j-amber/5'
            }`}>
              {status?.valid ? (
                <>
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle size={14} className="text-j-green" />
                    <span className="text-j-green font-mono text-[11px] tracking-[0.1em] uppercase font-semibold">
                      Valid
                    </span>
                  </div>
                  <div className="font-mono text-[10px] text-j-muted space-y-1">
                    <div>RMSE: <span className="text-j-text">{status.rmse?.toFixed(4)}px</span></div>
                    <div>Points: <span className="text-j-text">{status.point_count}</span></div>
                    {status.captured_at && (
                      <div>Captured: <span className="text-j-text">
                        {new Date(status.captured_at).toLocaleDateString()}
                      </span></div>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <div className="flex items-center gap-2 mb-1">
                    <AlertTriangle size={14} className="text-j-amber" />
                    <span className="text-j-amber font-mono text-[11px] tracking-[0.1em] uppercase font-semibold">
                      Not calibrated
                    </span>
                  </div>
                  <div className="font-mono text-[10px] text-j-muted">
                    Calibration required before normal operation
                  </div>
                </>
              )}
            </div>
          </section>

          {/* Session progress */}
          <section>
            <h3 className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase mb-3">
              Session Progress
            </h3>
            <div className="border border-j-border rounded-sm p-3 space-y-3">
              <div>
                <div className="flex justify-between font-mono text-[10px] text-j-muted mb-1.5">
                  <span>Captures</span>
                  <span className={sessionReady ? 'text-j-green' : 'text-j-text'}>
                    {sessionCaps} / {MIN}
                  </span>
                </div>
                <div className="w-full h-1 bg-j-border rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      sessionReady ? 'bg-j-green' : 'bg-j-cyan'
                    }`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>

              {lastCapture && (
                <div className={`font-mono text-[10px] ${lastCapture.accepted ? 'text-j-green' : 'text-j-amber'}`}>
                  Last: {lastCapture.accepted
                    ? `✓ Accepted — ${lastCapture.corners_found} corners`
                    : `✗ Rejected — ${lastCapture.corners_found} corners (need 6+)`}
                </div>
              )}
            </div>
          </section>

          {/* Compute result */}
          {lastCompute && (
            <section>
              <h3 className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase mb-3">
                Compute Result
              </h3>
              <div className="border border-j-green bg-j-green/5 rounded-sm p-3">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle size={14} className="text-j-green" />
                  <span className="text-j-green font-mono text-[11px] tracking-[0.1em] uppercase font-semibold">
                    Calibration Complete
                  </span>
                </div>
                <div className="font-mono text-[10px] text-j-muted space-y-1">
                  <div>RMSE: <span className="text-j-text">{lastCompute.rmse.toFixed(4)}px</span></div>
                  <div>Points: <span className="text-j-text">{lastCompute.point_count}</span></div>
                </div>
              </div>
            </section>
          )}

          {/* Error */}
          {error && (
            <div className="border border-j-red bg-j-red/5 rounded-sm p-3">
              <div className="text-j-red font-mono text-[10px] break-words">{error}</div>
            </div>
          )}

          {/* Instructions */}
          <section>
            <h3 className="text-j-muted font-mono text-[10px] tracking-[0.2em] uppercase mb-3">
              Instructions
            </h3>
            <ol className="space-y-2">
              {[
                'Place ChArUco board flat on the mat',
                `Capture ${MIN} valid frames from different angles`,
                'Keep the board fully visible in frame',
                'Click COMPUTE when all captures are done',
              ].map((step, i) => (
                <li key={i} className="flex gap-2 font-mono text-[10px] text-j-muted">
                  <span className="text-j-cdim flex-shrink-0">{i + 1}.</span>
                  {step}
                </li>
              ))}
            </ol>
          </section>
        </div>

        {/* Action buttons */}
        <div className="p-5 border-t border-j-border space-y-2 flex-shrink-0">
          <button
            onClick={capture}
            disabled={capturing}
            className="w-full py-2.5 bg-j-cyan/10 border border-j-cyan text-j-cyan
                       font-sans font-bold text-[12px] tracking-[0.2em] uppercase
                       hover:bg-j-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors duration-150 rounded-sm"
          >
            {capturing
              ? <span className="flex items-center justify-center gap-2"><RefreshCw size={12} className="animate-spin" /> CAPTURING...</span>
              : 'CAPTURE FRAME'}
          </button>

          <button
            onClick={compute}
            disabled={computing || !sessionReady}
            className="w-full py-2.5 bg-j-green/10 border border-j-green text-j-green
                       font-sans font-bold text-[12px] tracking-[0.2em] uppercase
                       hover:bg-j-green/20 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors duration-150 rounded-sm"
          >
            {computing
              ? <span className="flex items-center justify-center gap-2"><RefreshCw size={12} className="animate-spin" /> COMPUTING...</span>
              : `COMPUTE (${sessionCaps}/${MIN})`}
          </button>

          <button
            onClick={handleReset}
            onBlur={() => setResetConfirm(false)}
            className={`w-full py-2 border font-sans font-semibold text-[11px] tracking-[0.15em] uppercase
                        transition-colors duration-150 rounded-sm
                        ${resetConfirm
                          ? 'border-j-red bg-j-red/10 text-j-red hover:bg-j-red/20'
                          : 'border-j-border text-j-muted hover:text-j-text hover:border-j-muted'}`}
          >
            {resetConfirm ? '⚠ CONFIRM RESET' : 'RESET'}
          </button>
        </div>
      </div>
    </div>
  )
}
