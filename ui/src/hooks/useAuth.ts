import { useCallback, useEffect, useState } from 'react'
import {
  fetchAuthMe,
  login as apiLogin,
  logout as apiLogout,
  setOnAuthExpired,
  type AuthMe,
} from '../api/client'

export type AuthStatus = 'unknown' | 'authed' | 'anon'

export interface UseAuth {
  status: AuthStatus
  username: string | null
  authEnabled: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

/**
 * Single source of truth for "am I logged in". On mount calls /api/auth/me;
 * on any 401 from elsewhere in the app, the global handler in client.ts
 * trips this hook back to 'anon' so the gate drops the user to login.
 */
export function useAuth(): UseAuth {
  const [me, setMe] = useState<AuthMe | null>(null)
  const [status, setStatus] = useState<AuthStatus>('unknown')

  const refresh = useCallback(async () => {
    try {
      const next = await fetchAuthMe()
      setMe(next)
      setStatus(next.authenticated ? 'authed' : 'anon')
    } catch {
      // /api/auth/me unreachable — treat as anon so the gate shows login.
      setMe({ username: null, auth_enabled: true, authenticated: false })
      setStatus('anon')
    }
  }, [])

  useEffect(() => {
    refresh()
    setOnAuthExpired(() => setStatus('anon'))
    return () => setOnAuthExpired(null)
  }, [refresh])

  const login = useCallback(async (username: string, password: string) => {
    const next = await apiLogin(username, password)
    setMe(next)
    setStatus('authed')
  }, [])

  const logout = useCallback(async () => {
    try { await apiLogout() } catch { /* ignore */ }
    setMe(null)
    setStatus('anon')
  }, [])

  return {
    status,
    username: me?.username ?? null,
    authEnabled: me?.auth_enabled ?? true,
    login,
    logout,
  }
}
