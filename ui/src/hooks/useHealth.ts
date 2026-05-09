import { useEffect, useState } from 'react'
import { fetchHealth, type HealthResponse } from '../api/client'

export function useHealth(intervalMs = 5000) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function poll() {
      try {
        setHealth(await fetchHealth())
        setError(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error')
      }
    }
    poll()
    const id = setInterval(poll, intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])

  return { health, error }
}
