export interface HealthResponse {
  status: string
  version: string
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

// ── Gallery API────────────────────────────────────────────────────

export interface GalleryItem {
  id: string
  filename: string
  r2_key: string
  content_type: string
  file_size: number | null
  source: string
  created_at: string
}

export interface GalleryListResponse {
  items: GalleryItem[]
  total: number
  limit: number
  offset: number
}

export interface Generate3dResult {
  task_id: string
  mode: string
  project_id: string
  gallery_item_id: string
}

export interface GenerateSvgResult {
  svg: string
  gallery_item_id: string
}

async function _checkGallery<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.json().catch(() => ({})) as { detail?: string; error?: string }
    throw new Error(body.detail ?? body.error ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function fetchGallery(limit = 50, offset = 0): Promise<GalleryListResponse> {
  return _checkGallery(await fetch(`/api/gallery?limit=${limit}&offset=${offset}`))
}

export async function deleteGalleryItem(id: string): Promise<{ deleted: string }> {
  return _checkGallery(await fetch(`/api/gallery/${id}`, { method: 'DELETE' }))
}

export function galleryImageUrl(id: string): string {
  return `/api/gallery/${id}/image`
}

export async function galleryGenerate3d(id: string): Promise<Generate3dResult> {
  return _checkGallery(await fetch(`/api/gallery/${id}/generate-3d`, { method: 'POST' }))
}

export async function galleryGenerateSvg(id: string): Promise<GenerateSvgResult> {
  return _checkGallery(await fetch(`/api/gallery/${id}/generate-svg`, { method: 'POST' }))
}

// ── Generate API───────────────────────────────────────────────────

export interface StlResult {
  name: string
  filename: string
  size_bytes: number
  download_url: string
}

export async function compileOpenscad(scadCode: string, name: string): Promise<StlResult> {
  return _checkScan(await fetch('/api/generate/openscad', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scad_code: scadCode, name }),
  }))
}

// ── Print Queue API─────────────────────────────────────────────────

export interface PrinterStatus {
  state?: string
  nozzle_temp?: number
  bed_temp?: number
  progress?: number
  current_file?: string | null
  error?: string
}

export interface StlFile {
  filename: string
  stem: string
  size_bytes: number
  modified_at: number
}

export interface PrintProfile {
  id: string
  name: string
  layer_height: number
  infill_percent: number
  supports: 'none' | 'normal' | 'tree'
  is_builtin: boolean
}

export interface PrintJob {
  id: string
  name: string
  stl_path: string
  profile_id: string
  state: 'queued' | 'slicing' | 'uploading' | 'printing' | 'done' | 'failed' | 'cancelled'
  created_at: string
  started_at: string | null
  completed_at: string | null
  error: string | null
  three_mf_path: string | null
  progress: number
}

export interface PrintQueueResponse {
  active: PrintJob[]
  history: PrintJob[]
}

async function _checkPrint<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.json().catch(() => ({})) as { detail?: string; error?: string }
    throw new Error(body.detail ?? body.error ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function fetchPrinterStatus(): Promise<PrinterStatus> {
  return _checkPrint(await fetch('/api/print/status'))
}

export async function fetchStls(): Promise<{ stls: StlFile[] }> {
  return _checkPrint(await fetch('/api/print/stls'))
}

export async function fetchPrintQueue(): Promise<PrintQueueResponse> {
  return _checkPrint(await fetch('/api/print/queue'))
}

export async function queuePrintJob(
  stl_filename: string,
  profile_id: string,
  name?: string,
): Promise<PrintJob> {
  return _checkPrint(await fetch('/api/print/queue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stl_filename, profile_id, name: name ?? '' }),
  }))
}

export async function cancelPrintJob(jobId: string): Promise<{ cancelled: string }> {
  return _checkPrint(await fetch(`/api/print/queue/${jobId}`, { method: 'DELETE' }))
}

export async function fetchPrintProfiles(): Promise<{ profiles: PrintProfile[] }> {
  return _checkPrint(await fetch('/api/print/profiles'))
}

export async function createPrintProfile(body: {
  name: string
  layer_height: number
  infill_percent: number
  supports: string
}): Promise<PrintProfile> {
  return _checkPrint(await fetch('/api/print/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export async function deletePrintProfile(profileId: string): Promise<{ deleted: string }> {
  return _checkPrint(await fetch(`/api/print/profiles/${profileId}`, { method: 'DELETE' }))
}

// ── Voice Bridge API───────────────────────────────────────────────

export interface VoiceStatus {
  running: boolean
  state: 'idle' | 'listening' | 'thinking' | 'speaking'
  stt_url: string
  tts_url: string
  llm_url: string
  stt_port: number
  tts_port: number
  wake_sensitivity: number
  ha_integration: boolean
  history_turns: number
  conversation_id: string | null
}

export interface VoiceTurn {
  user: string
  jarvis: string
}

export interface VoiceHistory {
  turns: VoiceTurn[]
  conversation_id: string | null
}

async function _checkVoice<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.json().catch(() => ({})) as { detail?: string; error?: string }
    throw new Error(body.detail ?? body.error ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function fetchVoiceStatus(): Promise<VoiceStatus> {
  return _checkVoice(await fetch('/api/voice/status'))
}

export async function fetchVoiceHistory(): Promise<VoiceHistory> {
  return _checkVoice(await fetch('/api/voice/history'))
}

export async function triggerVoice(): Promise<{ triggered: boolean; state: string }> {
  return _checkVoice(await fetch('/api/voice/trigger', { method: 'POST' }))
}

export async function clearVoiceHistory(): Promise<{ cleared: boolean }> {
  return _checkVoice(await fetch('/api/voice/history', { method: 'DELETE' }))
}

// ── Settings API───────────────────────────────────────────────────

export interface SettingsResponse {
  settings: Record<string, string>
  env_file_exists: boolean
}

async function _checkSettings<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.json().catch(() => ({})) as { detail?: string; error?: string }
    throw new Error(body.detail ?? body.error ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function fetchSettings(): Promise<SettingsResponse> {
  return _checkSettings(await fetch('/api/settings'))
}

export async function saveSettings(settings: Record<string, string>): Promise<{ saved: boolean; restart_required: boolean }> {
  return _checkSettings(await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings }),
  }))
}

export async function restartService(): Promise<{ restarting: boolean }> {
  return _checkSettings(await fetch('/api/settings/restart', { method: 'POST' }))
}

export interface ConnectionTestResult {
  ok: boolean
  detail: string
}

export async function testConnections(): Promise<{ results: Record<string, ConnectionTestResult> }> {
  return _checkSettings(await fetch('/api/settings/test'))
}

export async function bambuDryRun(): Promise<{ results: Record<string, ConnectionTestResult> }> {
  return _checkSettings(await fetch('/api/settings/test/bambu'))
}

export async function meshyTest(): Promise<ConnectionTestResult> {
  return _checkSettings(await fetch('/api/settings/test/meshy'))
}

export async function bambuCloudAuth(otp: string): Promise<{ ok: boolean; user_id: string; detail: string }> {
  return _checkSettings(await fetch('/api/settings/bambu-auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ otp }),
  }))
}
