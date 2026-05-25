import { Routes, Route, Navigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Scanner from './pages/Scanner'
import Print from './pages/Print'
import ModelSources from './pages/ModelSources'
import Gallery from './pages/Gallery'
import Settings from './pages/Settings'
import HomeAssistant from './pages/HomeAssistant'
import Login from './pages/Login'
import { useWebSocket } from './hooks/useWebSocket'
import { useHealth } from './hooks/useHealth'
import { useAuth } from './hooks/useAuth'

export default function App() {
  const auth = useAuth()

  if (auth.status === 'unknown') {
    return (
      <div className="flex w-full h-full items-center justify-center">
        <div className="flex items-center gap-3 text-j-cyan font-mono text-[11px] tracking-[0.2em] uppercase">
          <Loader2 size={14} className="animate-spin" />
          Authenticating
        </div>
      </div>
    )
  }

  if (auth.status === 'anon') {
    return <Login onLogin={auth.login} />
  }

  return <AuthedApp username={auth.username} onLogout={auth.logout} />
}

function AuthedApp({ username, onLogout }: { username: string | null; onLogout: () => Promise<void> }) {
  const logs = useWebSocket()
  const { health, error: healthError } = useHealth()

  return (
    <Layout logs={logs} health={health} healthError={healthError} username={username} onLogout={onLogout}>
      <Routes>
        <Route path="/"               element={<Dashboard health={health} healthError={healthError} />} />
        <Route path="/scanner"        element={<Scanner />} />
        <Route path="/gallery"        element={<Gallery />} />
        <Route path="/models"         element={<ModelSources />} />
        <Route path="/print"          element={<Print />} />
        <Route path="/home-assistant" element={<HomeAssistant health={health} />} />
        <Route path="/settings"       element={<Settings />} />
        <Route path="*"               element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
