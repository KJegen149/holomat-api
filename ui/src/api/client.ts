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
    ha_bridge: boolean
    ha_url: string
  }
  scanner: {
    background_captured: boolean
    library_count: number
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

// ── Scanner API ─────────────────────────────────────────────────────────────

export interface ScanObject {
  id: string
  captured_at: string
  pinned: boolean
  thumbnail_b64: string | null
  name: string
  brand: string | null
  model: string | null
  category: string
  confidence: number
  width_mm: number
  depth_mm: number
  area_mm2: number
  height_mm: number | null
  notes: string | null
}

export interface BackgroundStatus {
  captured: boolean
  captured_at: string | null
}

export interface LibraryResponse {
  items: Omit<ScanObject, 'thumbnail_b64'>[]
  count: number
}

export interface ManualObjectBody {
  name: string
  brand?: string
  model?: string
  category?: string
  width_mm: number
  depth_mm: number
  height_mm?: number
  notes?: string
}

export interface PatchObjectBody {
  name?: string
  brand?: string
  model?: string
  category?: string
  height_mm?: number
  pinned?: boolean
  notes?: string
}

async function _checkScan(r: Response) {
  if (!r.ok) {
    const body = await r.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function captureBackground(): Promise<{ status: string; captured_at: string }> {
  return _checkScan(await fetch('/api/scan/background', { method: 'POST' }))
}

export async function fetchBackgroundStatus(): Promise<BackgroundStatus> {
  return _checkScan(await fetch('/api/scan/background/status'))
}

export async function scanCapture(): Promise<ScanObject> {
  return _checkScan(await fetch('/api/scan/capture', { method: 'POST' }))
}

export async function fetchLibrary(): Promise<LibraryResponse> {
  return _checkScan(await fetch('/api/scan/library'))
}

export async function fetchScanObject(id: string): Promise<ScanObject> {
  return _checkScan(await fetch(`/api/scan/library/${id}`))
}

export async function addManualObject(body: ManualObjectBody): Promise<ScanObject> {
  return _checkScan(await fetch('/api/scan/library', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export async function patchScanObject(id: string, body: PatchObjectBody): Promise<ScanObject> {
  return _checkScan(await fetch(`/api/scan/library/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export async function deleteScanObject(id: string): Promise<void> {
  const r = await fetch(`/api/scan/library/${id}`, { method: 'DELETE' })
  if (!r.ok) {
    const body = await r.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
}

export async function generateCase(objectId: string, paddingMm = 2, wallMm = 2): Promise<{ object_id: string; name: string; code: string }> {
  return _checkScan(await fetch('/api/scan/generate-case', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ object_id: objectId, padding_mm: paddingMm, wall_mm: wallMm }),
  }))
}
