import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Calibration from './pages/Calibration'
import Scanner from './pages/Scanner'
import Print from './pages/Print'
import Gallery from './pages/Gallery'
import Settings from './pages/Settings'
import HomeAssistant from './pages/HomeAssistant'
import { useWebSocket } from './hooks/useWebSocket'
import { useHealth } from './hooks/useHealth'

export default function App() {
  const logs = useWebSocket()
  const { health, error: healthError } = useHealth()

  return (
    <Layout logs={logs} health={health} healthError={healthError}>
      <Routes>
        <Route path="/"            element={<Dashboard health={health} healthError={healthError} />} />
        <Route path="/calibration"    element={<Calibration />} />
        <Route path="/home-assistant" element={<HomeAssistant health={health} />} />
        <Route path="/scanner"        element={<Scanner />} />
        <Route path="/print"       element={<Print />} />
        <Route path="/gallery"     element={<Gallery />} />
        <Route path="/settings"    element={<Settings />} />
        <Route path="*"            element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
