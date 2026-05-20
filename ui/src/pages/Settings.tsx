import { useEffect, useState, useCallback } from 'react'
import { Settings as SettingsIcon, Save, Loader2, RotateCcw, CheckCircle } from 'lucide-react'
import { fetchSettings, saveSettings } from '../api/client'

// ── Field & section definitions ─────────────────────────────────────────────

type FieldType = 'text' | 'password' | 'select' | 'toggle'

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
      { key: 'BAMBU_SERIAL',      label: 'Serial Number',          type: 'text',     placeholder: '01P00C…' },
      { key: 'BAMBU_IP',          label: 'LAN IP Address',         type: 'text',     placeholder: '10.11.12.91' },
      { key: 'BAMBU_ACCESS_CODE', label: 'Access Code',            type: 'password', hint: 'Settings → Network on printer' },
      { key: 'BAMBU_EMAIL',       label: 'Bambu Account Email',    type: 'text',     placeholder: 'you@example.com' },
      { key: 'BAMBU_PASSWORD',    label: 'Bambu Account Password', type: 'password' },
      { key: 'BAMBU_REGION',      label: 'Region',                 type: 'select',   options: ['global', 'china'] },
      { key: 'BAMBU_CERT',        label: 'Printer Cert Path',      type: 'text',     placeholder: '/home/jarvis/holomat-api/certs/printer.pem' },
    ],
  },
  {
    id: 'gemini',
    label: 'Gemini AI',
    fields: [
      { key: 'GEMINI_API_KEY', label: 'API Key', type: 'password', hint: 'Required for object scanning (Phase 4)' },
      { key: 'GEMINI_MODEL',   label: 'Model',   type: 'text',     placeholder: 'gemini-2.5-flash' },
    ],
  },
  {
    id: 'ha',
    label: 'Home Assistant',
    fields: [
      { key: 'HA_URL',       label: 'HA URL',           type: 'text',     placeholder: 'https://ha.example.com' },
      { key: 'HA_MQTT_HOST', label: 'MQTT Host',        type: 'text',     placeholder: '10.11.12.x' },
      { key: 'HA_MQTT_PORT', label: 'MQTT Port',        type: 'text',     placeholder: '1883' },
      { key: 'HA_MQTT_USER', label: 'MQTT User',        type: 'text' },
      { key: 'HA_MQTT_PASS', label: 'MQTT Password',   type: 'password' },
      { key: 'HA_TOKEN',     label: 'Long-Lived Token', type: 'password', hint: 'Settings → Profile → Long-Lived Tokens' },
    ],
  },
  {
    id: 'cloudflare',
    label: 'Cloudflare',
    fields: [
      { key: 'CF_API_URL', label: 'Worker URL', type: 'text',     placeholder: 'https://jarvis-api.kjeg.workers.dev' },
      { key: 'CF_API_KEY', label: 'API Key',    type: 'password', hint: 'Required — set after install' },
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
      { key: 'WYOMING_ENABLED',          label: 'Enable Voice Bridge',   type: 'toggle' },
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
]

const SENSITIVE_KEYS = new Set([
  'BAMBU_PASSWORD', 'BAMBU_ACCESS_CODE',
  'GEMINI_API_KEY', 'CF_API_KEY',
  'HA_MQTT_PASS', 'HA_TOKEN',
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
            key={field.key}
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

// ── Main Settings page ───────────────────────────────────────────────────────

export default function Settings() {
  const [serverValues, setServerValues] = useState<Record<string, string>>({})
  const [formValues, setFormValues]     = useState<Record<string, string>>({})
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState<string | null>(null)
  const [saving, setSaving]             = useState(false)
  const [savedSection, setSavedSection] = useState<string | null>(null)
  const [restartRequired, setRestartRequired] = useState(false)
  const [activeSection, setActiveSection]     = useState(SECTIONS[0].id)

  const load = useCallback(async (isInitial = false) => {
    try {
      const res = await fetchSettings()
      setServerValues(res.settings)
      if (isInitial) {
        const initial: Record<string, string> = {}
        for (const [key, val] of Object.entries(res.settings)) {
          initial[key] = SENSITIVE_KEYS.has(key) ? '' : val
        }
        setFormValues(initial)
      }
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load settings')
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
          if (SENSITIVE_KEYS.has(field.key)) next[field.key] = ''
        }
        return next
      })
      setTimeout(() => setSavedSection(null), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }, [formValues, load])

  const currentSection = SECTIONS.find(s => s.id === activeSection) ?? SECTIONS[0]

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
          <span className="text-j-muted font-mono text-[10px] tracking-[0.1em]">Phase 9</span>
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
          <div className="m-4 p-3 border border-j-amber/40 rounded-sm bg-j-amber/5">
            <div className="flex items-start gap-2">
              <RotateCcw size={11} className="text-j-amber flex-shrink-0 mt-0.5" />
              <p className="text-j-amber font-mono text-[9px] leading-relaxed tracking-[0.05em]">
                Restart required.<br />
                <span className="text-j-cdim font-mono text-[9px] break-all">
                  sudo systemctl restart holomat-api
                </span>
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Right panel — active section form */}
      <div className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4 border border-j-err/40 bg-j-err/5 rounded-sm px-4 py-3">
            <p className="text-j-err font-mono text-[11px]">{error}</p>
          </div>
        )}

        <SectionPanel
          section={currentSection}
          serverValues={serverValues}
          formValues={formValues}
          onChange={handleChange}
          onSave={handleSave}
          saving={saving}
          savedSection={savedSection}
        />
      </div>
    </div>
  )
}
