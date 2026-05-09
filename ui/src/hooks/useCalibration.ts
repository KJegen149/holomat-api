import { useCallback, useEffect, useState } from 'react'
import {
  fetchCalibrationStatus,
  captureFrame,
  computeCalibration,
  resetCalibration,
  type CalibrationStatus,
  type CaptureResult,
  type ComputeResult,
} from '../api/client'

export type { CalibrationStatus, CaptureResult, ComputeResult }

export function useCalibration() {
  const [status, setStatus]           = useState<CalibrationStatus | null>(null)
  const [capturing, setCapturing]     = useState(false)
  const [computing, setComputing]     = useState(false)
  const [lastCapture, setLastCapture] = useState<CaptureResult | null>(null)
  const [lastCompute, setLastCompute] = useState<ComputeResult | null>(null)
  const [error, setError]             = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setStatus(await fetchCalibrationStatus())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch status')
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 3000)
    return () => clearInterval(id)
  }, [refresh])

  const capture = useCallback(async () => {
    setCapturing(true)
    setError(null)
    try {
      const r = await captureFrame()
      setLastCapture(r)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Capture failed')
    } finally {
      setCapturing(false)
    }
  }, [refresh])

  const compute = useCallback(async () => {
    setComputing(true)
    setError(null)
    setLastCompute(null)
    try {
      const r = await computeCalibration()
      setLastCompute(r)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Compute failed')
    } finally {
      setComputing(false)
    }
  }, [refresh])

  const reset = useCallback(async () => {
    setError(null)
    try {
      await resetCalibration()
      setLastCapture(null)
      setLastCompute(null)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reset failed')
    }
  }, [refresh])

  return { status, capturing, computing, lastCapture, lastCompute, error, capture, compute, reset }
}
