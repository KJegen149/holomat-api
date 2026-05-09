import { Settings as SettingsIcon } from 'lucide-react'
import PhaseStub from '../components/PhaseStub'

export default function Settings() {
  return (
    <PhaseStub
      phase="9+"
      title="Settings"
      description="System configuration, hardware setup, environment management, and diagnostic tools for the Holomat platform."
      icon={SettingsIcon}
      capabilities={[
        'Environment variable management',
        'Bambu printer credential configuration',
        'Cloudflare API key setup',
        'ChArUco board geometry overrides',
        'Slicer profile editor',
        'System diagnostics and log export',
      ]}
    />
  )
}
