export interface HealthResponse {
  status: string
  version: string
  phase: string
  timestamp: string
  system: {
    platform: string
    python: string
  }
  calibration: {
    valid: boolean
    captured_at: string | null
    point_count: number
    rmse: number | null
  }
  hardware: {
    camera_detected: boolean
    printer_configured: boolean
    orca_slicer: boolean
    openscad: boolean
  }
  services: {
    smb_watcher: boolean
    ws_clients: number
    cf_api_url: string
    cf_api_key_set: boolean
  }
}

export interface CalibrationStatus {
  valid: boolean
  captured_at: string | null
  point_count: number
  rmse: number | null
  min_captures_required: number
  max_rmse: number
  session_captures: number
  session_ready: boolean
}

export interface CaptureResult {
  accepted: boolean
  markers_found: number
  corners_found: number
  capture_count: number
  ready_to_compute: boolean
  min_captures_required: number
}

export interface ComputeResult {
  success: boolean
  rmse: number
  point_count: number
  captured_at: string
}

export async function fetchHealth(): Promise<HealthResponse> {
  const r = await fetch('/api/health')
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function fetchCalibrationStatus(): Promise<CalibrationStatus> {
  const r = await fetch('/api/calibration/status')
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function captureFrame(): Promise<CaptureResult> {
  const r = await fetch('/api/calibration/capture', { method: 'POST' })
  if (!r.ok) {
    const body = await r.json().catch(() => ({}))
    throw new Error((body as { error?: string }).error ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function computeCalibration(): Promise<ComputeResult> {
  const r = await fetch('/api/calibration/compute', { method: 'POST' })
  if (!r.ok) {
    const body = await r.json().catch(() => ({})) as { detail?: string; error?: string }
    throw new Error(body.detail ?? body.error ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function resetCalibration(): Promise<void> {
  const r = await fetch('/api/calibration/reset', { method: 'DELETE' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
}
