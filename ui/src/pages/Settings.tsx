import { useEffect, useState, useCallback } from 'react'
import { Settings as SettingsIcon, Save, Loader2, RotateCcw, CheckCircle, Power, Zap, Circle, Lock } from 'lucide-react'
import { fetchSettings, saveSettings, restartService, testConnections, bambuDryRun, bambuCloudAuth, meshyTest, fetchHealth, setAdminKey, AdminAuthError, type ConnectionTestResult } from '../api/client'

// ── Field & section definitions ─────────────────────────────────────────────

type FieldType = 'text' | 'password' | 'select' | 'toggle' | 'header'

interface FieldDef {
  key: string
  label: string
  type: FieldType
  placeholder?: string
  options?: string[]
  hint?: string
}

interface SectionDef {
  id: string
  label: string
  fields: FieldDef[]
}

const SECTIONS: SectionDef[] = [
  {
    id: 'printer',
    label: 'Bambu Printer',
    fields: [
      { key: 'BAMBU_SERIAL',      label: 'Serial Number',          type: 'text',     placeholder: 'serial number' },
      { key: 'BAMBU_IP',          label: 'LAN IP Address',         type: 'text',     placeholder: '192.168.1.50' },
      { key: 'BAMBU_ACCESS_CODE', label: 'Access Code',            type: 'password', hint: 'Settings → Network on printer' },
      { key: 'BAMBU_AMS_SLOT',    label: 'AMS Filament Slot',      type: 'text',     placeholder: '0', hint: '0-indexed slot; leave blank for default' },
      { key: 'BAMBU_EMAIL',       label: 'Bambu Account Email',    type: 'text',     placeholder: 'you@example.com' },
      { key: 'BAMBU_PASSWORD',    label: 'Bambu Account Password', type: 'password' },
      { key: 'BAMBU_REGION',      label: 'Region',                 type: 'select',   options: ['global', 'china'] },
      { key: 'BAMBU_CERT',        label: 'Printer Cert Path',      type: 'text',     placeholder: 'certs/printer.pem' },
    ],
  },
  {
    id: 'apis',
    label: 'External APIs',
    fields: [
      { key: '',               label: 'GEMINI AI',          type: 'header' },
      { key: 'GEMINI_API_KEY', label: 'API Key',            type: 'password', hint: 'Vision (object scan) + text generation (case design)' },
      { key: 'GEMINI_MODEL',   label: 'Model',              type: 'text',     placeholder: 'gemini-2.5-flash' },
      { key: '',               label: 'CLOUDFLARE WORKER',  type: 'header' },
      { key: 'CF_API_URL',     label: 'Worker URL',         type: 'text',     placeholder: 'https://your-worker.workers.dev', hint: 'Proxies Gallery storage, Meshy 3D generation, and Voice AI (STT / TTS / LLM)' },
      { key: 'CF_API_KEY',     label: 'Worker API Key',     type: 'password' },
      { key: '',                 label: 'THINGIVERSE',      type: 'header' },
      { key: 'THINGIVERSE_TOKEN', label: 'App Token',       type: 'password', hint: 'Register an app at thingiverse.com/developers/my-apps and copy its token' },
    ],
  },
  {
    id: 'ha',
    label: 'Home Assistant',
    fields: [
      { key: 'HA_URL',       label: 'HA URL',           type: 'text',     placeholder: 'https://ha.example.com' },
      { key: 'HA_MQTT_HOST', label: 'MQTT Host',        type: 'text',     placeholder: '192.168.1.x' },
      { key: 'HA_MQTT_PORT', label: 'MQTT Port',        type: 'text',     placeholder: '1883' },
      { key: 'HA_MQTT_USER', label: 'MQTT User',        type: 'text' },
      { key: 'HA_MQTT_PASS', label: 'MQTT Password',   type: 'password' },
      { key: 'HA_TOKEN',     label: 'Long-Lived Token', type: 'password', hint: 'Settings → Profile → Long-Lived Tokens' },
    ],
  },
  {
    id: 'hardware',
    label: 'Hardware',
    fields: [
      { key: 'CAMERA_DEVICE', label: 'Camera Device Index', type: 'text', placeholder: '0' },
      { key: 'ORCA_CLI',      label: 'OrcaSlicer Binary',   type: 'text', placeholder: '/usr/bin/orca-slicer' },
      { key: 'OPENSCAD_BIN', label: 'OpenSCAD Binary',     type: 'text', placeholder: 'openscad' },
    ],
  },
  {
    id: 'voice',
    label: 'Voice Bridge',
    fields: [
      { key: 'WYOMING_ENABLED',          label: 'Enable Voice Bridge',   type: 'toggle', hint: 'Save then restart service (Administration tab) to activate' },
      { key: 'WYOMING_STT_PORT',         label: 'STT Server Port',       type: 'text', placeholder: '10300' },
      { key: 'WYOMING_TTS_PORT',         label: 'TTS Server Port',       type: 'text', placeholder: '10200' },
      { key: 'WYOMING_WAKE_SENSITIVITY', label: 'Wake Word Sensitivity', type: 'text', placeholder: '0.5', hint: '0.0–1.0, lower = more sensitive' },
      { key: 'WYOMING_MIC_INDEX',        label: 'Mic Device Index',      type: 'text', placeholder: 'system default' },
      { key: 'WYOMING_SPEAKER_INDEX',    label: 'Speaker Device Index',  type: 'text', placeholder: 'system default' },
      { key: 'WYOMING_STT_URL',          label: 'STT Worker URL',        type: 'text', placeholder: 'https://wyoming-stt.kjeg.workers.dev' },
      { key: 'WYOMING_TTS_URL',          label: 'TTS Worker URL',        type: 'text', placeholder: 'https://wyoming-tts.kjeg.workers.dev' },
      { key: 'WYOMING_LLM_URL',          label: 'LLM Worker URL',        type: 'text', placeholder: 'https://wyoming-llm.kjeg.workers.dev' },
    ],
  },
  {
    id: 'administration',
    label: 'Administration',
    fields: [],
  },
]

const SENSITIVE_KEYS = new Set([
  'BAMBU_PASSWORD', 'BAMBU_ACCESS_CODE',
  'GEMINI_API_KEY', 'CF_API_KEY',
  'HA_MQTT_PASS', 'HA_TOKEN',
  'THINGIVERSE_TOKEN',
])

const MASK = '••••••'

// ── FieldRow component ───────────────────────────────────────────────────────

interface FieldRowProps {
  field: FieldDef
  serverValue: string
  value: string
  onChange: (key: string, val: string) => void
}

function FieldRow({ field, serverValue, value, onChange }: FieldRowProps) {
  const isSet = serverValue === MASK

  const inputBase =
    'w-full bg-j-bg border border-j-border rounded-sm px-3 py-2 ' +
    'font-mono text-[11px] text-j-text placeholder-j-cdim ' +
    'focus:outline-none focus:border-j-cyan transition-colors'

  if (field.type === 'header') {
    return (
      <div className="flex items-center gap-3 pt-4 pb-1 first:pt-0">
        <span className="font-mono text-[10px] font-bold tracking-[0.15em] text-j-cyan">{field.label}</span>
        <div className="flex-1 h-px bg-j-border" />
      </div>
    )
  }

  if (field.type === 'toggle') {
    const isTrue = value === 'true'
    return (
      <div className="flex items-center justify-between py-2">
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-[11px] text-j-text tracking-[0.05em]">{field.label}</span>
          {field.hint && <span className="font-mono text-[10px] text-j-cdim">{field.hint}</span>}
        </div>
        <button
          type="button"
          onClick={() => onChange(field.key, isTrue ? 'false' : 'true')}
          className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 border ${
            isTrue ? 'bg-j-cyan/20 border-j-cyan' : 'bg-j-bg border-j-border'
          }`}
        >
          <span className={`absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all ${
            isTrue ? 'left-[calc(100%-18px)] bg-j-cyan' : 'left-0.5 bg-j-muted'
          }`} />
        </button>
      </div>
    )
  }

  if (field.type === 'select') {
    return (
      <div className="flex flex-col gap-1.5">
        <label className="font-mono text-[10px] text-j-muted tracking-[0.12em] uppercase">
          {field.label}
        </label>
        <select
          value={value}
          onChange={e => onChange(field.key, e.target.value)}
          className={inputBase + ' cursor-pointer'}
        >
          {field.options?.map(opt => (
            <option key={opt} value={opt} className="bg-j-bg">{opt}</option>
          ))}
        </select>
      </div>
    )
  }

  const placeholder = field.type === 'password' && isSet
    ? '••••••  (already set — type to change)'
    : (field.placeholder ?? '')

  return (
    <div className="flex flex-col gap-1.5">
      <label className="font-mono text-[10px] text-j-muted tracking-[0.12em] uppercase">
        {field.label}
        {field.type === 'password' && (
          <span className={`ml-2 text-[9px] ${isSet ? 'text-j-green' : 'text-j-amber'}`}>
            {isSet ? '● SET' : '○ NOT SET'}
          </span>
        )}
      </label>
      <input
        type={field.type === 'password' ? 'password' : 'text'}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(field.key, e.target.value)}
        className={inputBase}
        autoComplete="off"
        spellCheck={false}
      />
      {field.hint && <span className="font-mono text-[10px] text-j-cdim">{field.hint}</span>}
    </div>
  )
}

// ── SectionPanel component ───────────────────────────────────────────────────

interface SectionPanelProps {
  section: SectionDef
  serverValues: Record<string, string>
  formValues: Record<string, string>
  onChange: (key: string, val: string) => void
  onSave: (sectionId: string) => void
  saving: boolean
  savedSection: string | null
}

function SectionPanel({ section, serverValues, formValues, onChange, onSave, saving, savedSection }: SectionPanelProps) {
  const isSaved = savedSection === section.id

  return (
    <div className="border border-j-border rounded-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 bg-j-surf border-b border-j-border">
        <span className="font-mono text-[11px] text-j-cyan tracking-[0.15em] uppercase">
          {section.label}
        </span>
        <button
          type="button"
          disabled={saving}
          onClick={() => onSave(section.id)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm border
            font-mono text-[10px] tracking-[0.1em] uppercase transition-colors
            ${isSaved
              ? 'border-j-green text-j-green'
              : saving
              ? 'border-j-border text-j-muted cursor-not-allowed'
              : 'border-j-cyan text-j-cyan hover:bg-j-cyan/10 cursor-pointer'
            }`}
        >
          {saving
            ? <Loader2 size={11} className="animate-spin" />
            : isSaved
            ? <CheckCircle size={11} />
            : <Save size={11} />
          }
          {saving ? 'Saving…' : isSaved ? 'Saved' : 'Save'}
        </button>
      </div>

      <div className="px-5 py-4 space-y-4 bg-j-bg">
        {section.fields.map(field => (
          <FieldRow
            key={field.key || `__hdr_${field.label}`}
            field={field}
            serverValue={serverValues[field.key] ?? ''}
            value={formValues[field.key] ?? ''}
            onChange={onChange}
          />
        ))}
      </div>
    </div>
  )
}

// ── AdminPanel component ─────────────────────────────────────────────────────

type RestartState = 'idle' | 'restarting' | 'online' | 'timeout'

function AdminPanel() {
  const [restartState, setRestartState]     = useState<RestartState>('idle')
  const [testing, setTesting]               = useState(false)
  const [testResults, setTestResults]       = useState<Record<string, ConnectionTestResult> | null>(null)
  const [testError, setTestError]           = useState<string | null>(null)
  const [dryRunning, setDryRunning]         = useState(false)
  const [dryRunResults, setDryRunResults]   = useState<Record<string, ConnectionTestResult> | null>(null)
  const [dryRunError, setDryRunError]       = useState<string | null>(null)
  const [meshyTesting, setMeshyTesting]     = useState(false)
  const [meshyResult, setMeshyResult]       = useState<ConnectionTestResult | null>(null)
  const [meshyError, setMeshyError]         = useState<string | null>(null)

  const handleRestart = async () => {
    setRestartState('restarting')
    try {
      await restartService()
    } catch { /* server may die before responding — that's expected */ }

    // Wait for RestartSec=5 + startup time
    await new Promise(r => setTimeout(r, 6500))

    const deadline = Date.now() + 20000
    while (Date.now() < deadline) {
      try {
        await fetchHealth()
        setRestartState('online')
        setTimeout(() => setRestartState('idle'), 5000)
        return
      } catch { /* still starting */ }
      await new Promise(r => setTimeout(r, 1500))
    }
    setRestartState('timeout')
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResults(null)
    setTestError(null)
    try {
      const res = await testConnections()
      setTestResults(res.results)
    } catch (e) {
      setTestError(e instanceof Error ? e.message : 'Test failed')
    } finally {
      setTesting(false)
    }
  }

  const handleDryRun = async () => {
    setDryRunning(true)
    setDryRunResults(null)
    setDryRunError(null)
    try {
      const res = await bambuDryRun()
      setDryRunResults(res.results)
    } catch (e) {
      setDryRunError(e instanceof Error ? e.message : 'Dry run failed')
    } finally {
      setDryRunning(false)
    }
  }

  const handleMeshyTest = async () => {
    setMeshyTesting(true)
    setMeshyResult(null)
    setMeshyError(null)
    try {
      const res = await meshyTest()
      setMeshyResult(res)
    } catch (e) {
      setMeshyError(e instanceof Error ? e.message : 'Test failed')
    } finally {
      setMeshyTesting(false)
    }
  }

  const TEST_LABELS: Record<string, string> = {
    gemini:     'Gemini AI',
    cloudflare: 'Cloudflare Worker',
    ha_token:   'HA Long-Lived Token',
    ha_mqtt:    'HA MQTT Broker',
    bambu_lan:  'Bambu Printer LAN',
  }

  return (
    <div className="space-y-4">
      {/* Service Control */}
      <div className="border border-j-border rounded-sm overflow-hidden">
        <div className="px-5 py-3 bg-j-surf border-b border-j-border">
          <span className="font-mono text-[11px] text-j-cyan tracking-[0.15em] uppercase">
            Service Control
          </span>
        </div>
        <div className="px-5 py-4 bg-j-bg space-y-3">
          <p className="font-mono text-[10px] text-j-muted leading-relaxed">
            Restart the Holomat service to apply saved credential changes.
            The UI will reconnect automatically (~6–10 s).
          </p>
          <div className="flex items-center gap-4">
            <button
              type="button"
              disabled={restartState === 'restarting'}
              onClick={handleRestart}
              className={`flex items-center gap-2 px-4 py-2 rounded-sm border
                font-mono text-[10px] tracking-[0.1em] uppercase transition-colors
                ${restartState === 'restarting'
                  ? 'border-j-border text-j-muted cursor-not-allowed'
                  : restartState === 'online'
                  ? 'border-j-green text-j-green cursor-pointer'
                  : restartState === 'timeout'
                  ? 'border-j-amber text-j-amber cursor-pointer'
                  : 'border-j-red/60 text-j-red hover:bg-j-red/10 cursor-pointer'
                }`}
            >
              {restartState === 'restarting'
                ? <Loader2 size={12} className="animate-spin" />
                : restartState === 'online'
                ? <CheckCircle size={12} />
                : <Power size={12} />
              }
              {restartState === 'restarting' ? 'Restarting…'
                : restartState === 'online'    ? 'Back Online'
                : restartState === 'timeout'   ? 'Timed Out'
                : 'Restart Service'}
            </button>
            {restartState === 'restarting' && (
              <span className="font-mono text-[10px] text-j-muted animate-pulse">
                Waiting for service to come back…
              </span>
            )}
            {restartState === 'timeout' && (
              <span className="font-mono text-[10px] text-j-amber">
                Check: sudo journalctl -u holomat-api -n 50
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Connection Tests */}
      <div className="border border-j-border rounded-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 bg-j-surf border-b border-j-border">
          <span className="font-mono text-[11px] text-j-cyan tracking-[0.15em] uppercase">
            Test Connections
          </span>
          <button
            type="button"
            disabled={testing}
            onClick={handleTest}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm border
              font-mono text-[10px] tracking-[0.1em] uppercase transition-colors
              ${testing
                ? 'border-j-border text-j-muted cursor-not-allowed'
                : 'border-j-cyan text-j-cyan hover:bg-j-cyan/10 cursor-pointer'
              }`}
          >
            {testing ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
            {testing ? 'Testing…' : 'Run Tests'}
          </button>
        </div>
        <div className="px-5 py-4 bg-j-bg">
          {testError && (
            <p className="font-mono text-[11px] text-j-red mb-3">{testError}</p>
          )}
          {!testResults && !testing && (
            <p className="font-mono text-[10px] text-j-cdim">
              Validates saved credentials and network reachability for each service.
            </p>
          )}
          {testResults && (
            <div className="space-y-2">
              {Object.entries(testResults).map(([key, result]) => (
                <div key={key} className="flex items-start gap-3">
                  <Circle
                    size={8}
                    className={`flex-shrink-0 mt-0.5 fill-current ${result.ok ? 'text-j-green' : 'text-j-red'}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-[10px] text-j-text tracking-[0.05em] w-36 flex-shrink-0">
                        {TEST_LABELS[key] ?? key}
                      </span>
                      <span className={`font-mono text-[10px] ${result.ok ? 'text-j-green' : 'text-j-red'}`}>
                        {result.ok ? 'OK' : 'FAIL'}
                      </span>
                    </div>
                    <p className="font-mono text-[9px] text-j-cdim mt-0.5 break-all">
                      {result.detail}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Bambu Dry Run */}
      <div className="border border-j-border rounded-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 bg-j-surf border-b border-j-border">
          <div>
            <span className="font-mono text-[11px] text-j-cyan tracking-[0.15em] uppercase">
              Bambu Printer Dry Run
            </span>
            <p className="font-mono text-[9px] text-j-cdim mt-0.5">
              FTPS login · Cloud auth · Live MQTT status poll — no file sent, no print triggered. Allow ~30 s.
            </p>
          </div>
          <button
            type="button"
            disabled={dryRunning}
            onClick={handleDryRun}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm border
              font-mono text-[10px] tracking-[0.1em] uppercase transition-colors flex-shrink-0
              ${dryRunning
                ? 'border-j-border text-j-muted cursor-not-allowed'
                : 'border-j-cyan text-j-cyan hover:bg-j-cyan/10 cursor-pointer'
              }`}
          >
            {dryRunning ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
            {dryRunning ? 'Running…' : 'Dry Run'}
          </button>
        </div>
        <div className="px-5 py-4 bg-j-bg">
          {dryRunError && (
            <p className="font-mono text-[11px] text-j-red mb-3">{dryRunError}</p>
          )}
          {!dryRunResults && !dryRunning && (
            <p className="font-mono text-[10px] text-j-cdim">
              Tests the full print pipeline up to the point of sending a file.
            </p>
          )}
          {dryRunResults && (
            <div className="space-y-2">
              {Object.entries(dryRunResults).map(([key, result]) => (
                <div key={key} className="flex items-start gap-3">
                  <Circle
                    size={8}
                    className={`flex-shrink-0 mt-0.5 fill-current ${result.ok ? 'text-j-green' : 'text-j-red'}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-[10px] text-j-text tracking-[0.05em] w-36 flex-shrink-0">
                        {key === 'ftps_login'  ? 'FTPS Login'      :
                         key === 'cloud_auth'  ? 'Cloud Auth'      :
                         key === 'mqtt_status' ? 'MQTT Status Poll' : key}
                      </span>
                      <span className={`font-mono text-[10px] ${result.ok ? 'text-j-green' : 'text-j-red'}`}>
                        {result.ok ? 'OK' : 'FAIL'}
                      </span>
                    </div>
                    <p className="font-mono text-[9px] text-j-cdim mt-0.5 break-all">
                      {result.detail}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Meshy 3D Test */}
      <div className="border border-j-border rounded-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 bg-j-surf border-b border-j-border">
          <div>
            <span className="font-mono text-[11px] text-j-cyan tracking-[0.15em] uppercase">
              Meshy 3D API
            </span>
            <p className="font-mono text-[9px] text-j-cdim mt-0.5">
              Confirms CF worker can reach the Meshy API with the saved key.
            </p>
          </div>
          <button
            type="button"
            disabled={meshyTesting}
            onClick={handleMeshyTest}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-sm border
              font-mono text-[10px] tracking-[0.1em] uppercase transition-colors flex-shrink-0
              ${meshyTesting
                ? 'border-j-border text-j-muted cursor-not-allowed'
                : 'border-j-cyan text-j-cyan hover:bg-j-cyan/10 cursor-pointer'
              }`}
          >
            {meshyTesting ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
            {meshyTesting ? 'Testing…' : 'Test'}
          </button>
        </div>
        <div className="px-5 py-4 bg-j-bg">
          {meshyError && (
            <p className="font-mono text-[11px] text-j-red mb-3">{meshyError}</p>
          )}
          {!meshyResult && !meshyTesting && (
            <p className="font-mono text-[10px] text-j-cdim">
              Requires CF_API_URL and CF_API_KEY to be saved and the service restarted.
            </p>
          )}
          {meshyResult && (
            <div className="flex items-start gap-3">
              <Circle
                size={8}
                className={`flex-shrink-0 mt-0.5 fill-current ${meshyResult.ok ? 'text-j-green' : 'text-j-red'}`}
              />
              <div>
                <span className={`font-mono text-[10px] ${meshyResult.ok ? 'text-j-green' : 'text-j-red'}`}>
                  {meshyResult.ok ? 'OK' : 'FAIL'}
                </span>
                <p className="font-mono text-[9px] text-j-cdim mt-0.5 break-all">{meshyResult.detail}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── OTP panel — rendered below the Printer SectionPanel ──────────────────────

function BambuOtpPanel() {
  const [otp, setOtp]         = useState('')
  const [busy, setBusy]       = useState(false)
  const [result, setResult]   = useState<{ ok: boolean; detail: string } | null>(null)

  const handleAuth = async () => {
    setBusy(true)
    setResult(null)
    try {
      const res = await bambuCloudAuth(otp)
      setResult({ ok: res.ok, detail: res.detail })
      if (res.ok) setOtp('')
    } catch (e) {
      setResult({ ok: false, detail: e instanceof Error ? e.message : 'Auth failed' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 border border-j-border rounded-sm overflow-hidden">
      <div className="px-5 py-3 bg-j-surf border-b border-j-border">
        <span className="font-mono text-[11px] text-j-cyan tracking-[0.15em] uppercase">
          Cloud Authentication
        </span>
        <p className="font-mono text-[9px] text-j-cdim mt-0.5">
          Authenticate with Bambu cloud using saved credentials. Enter OTP only if prompted by MFA.
          Token is cached — re-run if auth expires.
        </p>
      </div>
      <div className="px-5 py-4 bg-j-bg space-y-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={otp}
            onChange={e => setOtp(e.target.value)}
            placeholder="OTP code (leave blank if not required)"
            className="flex-1 bg-j-bg border border-j-border rounded-sm px-3 py-2
              font-mono text-[11px] text-j-text placeholder-j-cdim
              focus:outline-none focus:border-j-cyan transition-colors"
            autoComplete="one-time-code"
            maxLength={8}
          />
          <button
            type="button"
            disabled={busy}
            onClick={handleAuth}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-sm border flex-shrink-0
              font-mono text-[10px] tracking-[0.1em] uppercase transition-colors
              ${busy
                ? 'border-j-border text-j-muted cursor-not-allowed'
                : 'border-j-cyan text-j-cyan hover:bg-j-cyan/10 cursor-pointer'
              }`}
          >
            {busy ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
            {busy ? 'Authenticating…' : 'Authenticate'}
          </button>
        </div>
        {result && (
          <p className={`font-mono text-[10px] ${result.ok ? 'text-j-green' : 'text-j-red'}`}>
            {result.ok ? '✓ ' : '✗ '}{result.detail}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main Settings page ───────────────────────────────────────────────────────

function AdminKeyGate({ onUnlock }: { onUnlock: () => void }) {
  const [key, setKey] = useState('')
  return (
    <div className="flex flex-col items-center justify-center h-full gap-5 p-10">
      <Lock size={32} className="text-j-amber" strokeWidth={1.5} />
      <div className="text-center">
        <h2 className="text-j-amber font-sans font-bold text-[13px] tracking-[0.2em] uppercase mb-1">
          Admin Key Required
        </h2>
        <p className="text-j-muted font-mono text-[10px] tracking-[0.05em]">
          The Settings API is protected — enter the HOLOMAT_ADMIN_KEY value.
        </p>
      </div>
      <form
        onSubmit={(e) => { e.preventDefault(); if (key) { setAdminKey(key); onUnlock() } }}
        className="flex flex-col gap-3 w-72"
      >
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="Admin key"
          autoFocus
          className="bg-j-bg border border-j-border rounded-sm px-3 py-2 text-j-text font-mono text-[12px] focus:border-j-cyan outline-none"
        />
        <button
          type="submit"
          disabled={!key}
          className="bg-j-cyan/10 border border-j-cyan text-j-cyan font-mono text-[11px] tracking-[0.15em] uppercase py-2 rounded-sm hover:bg-j-cyan/20 disabled:opacity-40 transition-colors"
        >
          Unlock
        </button>
      </form>
    </div>
  )
}


export default function Settings() {
  const [serverValues, setServerValues] = useState<Record<string, string>>({})
  const [formValues, setFormValues]     = useState<Record<string, string>>({})
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState<string | null>(null)
  const [saving, setSaving]             = useState(false)
  const [savedSection, setSavedSection] = useState<string | null>(null)
  const [restartRequired, setRestartRequired] = useState(false)
  const [activeSection, setActiveSection]     = useState(SECTIONS[0].id)
  const [needsKey, setNeedsKey]               = useState(false)
  const [authEnabled, setAuthEnabled]         = useState(true)

  const load = useCallback(async (isInitial = false) => {
    try {
      const res = await fetchSettings()
      setServerValues(res.settings)
      setAuthEnabled(res.auth_enabled)
      if (isInitial) {
        const initial: Record<string, string> = {}
        for (const [key, val] of Object.entries(res.settings)) {
          initial[key] = SENSITIVE_KEYS.has(key) ? '' : val
        }
        setFormValues(initial)
      }
      setError(null)
    } catch (e) {
      if (e instanceof AdminAuthError) setNeedsKey(true)
      else setError(e instanceof Error ? e.message : 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(true) }, [load])

  const handleChange = useCallback((key: string, val: string) => {
    setFormValues(prev => ({ ...prev, [key]: val }))
  }, [])

  const handleSave = useCallback(async (sectionId: string) => {
    const section = SECTIONS.find(s => s.id === sectionId)
    if (!section) return

    setSaving(true)
    setSavedSection(null)

    const payload: Record<string, string> = {}
    for (const field of section.fields) {
      if (!field.key) continue  // header dividers have no key
      const val = formValues[field.key] ?? ''
      if (SENSITIVE_KEYS.has(field.key)) {
        if (val && val !== MASK) payload[field.key] = val
      } else {
        payload[field.key] = val
      }
    }

    try {
      await saveSettings(payload)
      setSavedSection(sectionId)
      setRestartRequired(true)
      await load(false)
      // Reset sensitive fields to blank after save (server now shows them as ●SET)
      setFormValues(prev => {
        const next = { ...prev }
        for (const field of section.fields) {
          if (field.key && SENSITIVE_KEYS.has(field.key)) next[field.key] = ''
        }
        return next
      })
      setTimeout(() => setSavedSection(null), 3000)
    } catch (e) {
      if (e instanceof AdminAuthError) setNeedsKey(true)
      else setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }, [formValues, load])

  const currentSection = SECTIONS.find(s => s.id === activeSection) ?? SECTIONS[0]

  if (needsKey) {
    return <AdminKeyGate onUnlock={() => { setNeedsKey(false); setLoading(true); load(true) }} />
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="animate-spin text-j-cyan" />
      </div>
    )
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left sidebar — section nav */}
      <div className="w-52 flex-shrink-0 border-r border-j-border bg-j-surf flex flex-col overflow-y-auto">
        <div className="px-5 py-4 border-b border-j-border">
          <div className="flex items-center gap-2 mb-1">
            <SettingsIcon size={14} className="text-j-cyan" strokeWidth={1.5} />
            <span className="text-j-cyan font-mono text-[11px] tracking-[0.2em] uppercase">Settings</span>
          </div>
        </div>

        <nav className="py-2 flex-1">
          {SECTIONS.map(section => (
            <button
              key={section.id}
              type="button"
              onClick={() => setActiveSection(section.id)}
              className={`w-full text-left px-5 py-2.5 font-mono text-[10px] tracking-[0.12em] uppercase
                transition-colors cursor-pointer
                ${activeSection === section.id
                  ? 'text-j-cyan bg-j-border/40 border-r-2 border-j-cyan'
                  : 'text-j-muted hover:text-j-text hover:bg-j-border/20'
                }`}
            >
              {section.label}
            </button>
          ))}
        </nav>

        {restartRequired && (
          <button
            type="button"
            onClick={() => setActiveSection('administration')}
            className="m-4 p-3 border border-j-amber/40 rounded-sm bg-j-amber/5 text-left w-[calc(100%-2rem)] cursor-pointer hover:bg-j-amber/10 transition-colors"
          >
            <div className="flex items-start gap-2">
              <RotateCcw size={11} className="text-j-amber flex-shrink-0 mt-0.5" />
              <p className="text-j-amber font-mono text-[9px] leading-relaxed tracking-[0.05em]">
                Restart required.<br />
                <span className="text-j-cdim">Click to go to Administration →</span>
              </p>
            </div>
          </button>
        )}
      </div>

      {/* Right panel — active section form */}
      <div className="flex-1 overflow-y-auto p-6">
        {!authEnabled && (
          <div className="mb-4 border border-j-amber/40 bg-j-amber/5 rounded-sm px-4 py-3">
            <p className="text-j-amber font-mono text-[11px]">
              Settings API is unprotected — set HOLOMAT_ADMIN_KEY to require an admin key.
            </p>
          </div>
        )}
        {error && (
          <div className="mb-4 border border-j-red/40 bg-j-red/5 rounded-sm px-4 py-3">
            <p className="text-j-red font-mono text-[11px]">{error}</p>
          </div>
        )}

        {activeSection === 'administration'
          ? <AdminPanel />
          : <>
              <SectionPanel
                section={currentSection}
                serverValues={serverValues}
                formValues={formValues}
                onChange={handleChange}
                onSave={handleSave}
                saving={saving}
                savedSection={savedSection}
              />
              {activeSection === 'printer' && <BambuOtpPanel />}
            </>
        }
      </div>
    </div>
  )
}
