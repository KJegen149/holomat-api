import { useCallback, useEffect, useState } from 'react'
import {
  fetchPrinterStatus,
  fetchStls,
  fetchPrintQueue,
  fetchPrintProfiles,
  queuePrintJob,
  cancelPrintJob,
  createPrintProfile,
  deletePrintProfile,
  type PrinterStatus,
  type StlFile,
  type PrintJob,
  type PrintProfile,
} from '../api/client'

export type { PrinterStatus, StlFile, PrintJob, PrintProfile }

export function usePrint() {
  const [status, setStatus]           = useState<PrinterStatus | null>(null)
  const [stls, setStls]               = useState<StlFile[]>([])
  const [active, setActive]           = useState<PrintJob[]>([])
  const [history, setHistory]         = useState<PrintJob[]>([])
  const [profiles, setProfiles]       = useState<PrintProfile[]>([])
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState<string | null>(null)

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await fetchPrinterStatus())
    } catch {
      // non-fatal
    }
  }, [])

  const refreshQueue = useCallback(async () => {
    try {
      const q = await fetchPrintQueue()
      setActive(q.active)
      setHistory(q.history)
    } catch {
      // non-fatal
    }
  }, [])

  const refreshStls = useCallback(async () => {
    try {
      const r = await fetchStls()
      setStls(r.stls)
    } catch {
      // non-fatal
    }
  }, [])

  const refreshProfiles = useCallback(async () => {
    try {
      const r = await fetchPrintProfiles()
      setProfiles(r.profiles)
    } catch {
      // non-fatal
    }
  }, [])

  useEffect(() => {
    refreshStatus()
    refreshQueue()
    refreshStls()
    refreshProfiles()

    // Poll status every 5 s, queue every 8 s
    const statusId = setInterval(refreshStatus, 5_000)
    const queueId  = setInterval(refreshQueue,  8_000)
    return () => {
      clearInterval(statusId)
      clearInterval(queueId)
    }
  }, [refreshStatus, refreshQueue, refreshStls, refreshProfiles])

  const addJob = useCallback(async (
    stl_filename: string,
    profile_id: string,
    name?: string,
  ) => {
    setLoading(true)
    setError(null)
    try {
      await queuePrintJob(stl_filename, profile_id, name)
      await refreshQueue()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to queue job')
    } finally {
      setLoading(false)
    }
  }, [refreshQueue])

  const cancelJob = useCallback(async (jobId: string) => {
    setError(null)
    try {
      await cancelPrintJob(jobId)
      await refreshQueue()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to cancel job')
    }
  }, [refreshQueue])

  const addProfile = useCallback(async (body: {
    name: string
    layer_height: number
    infill_percent: number
    supports: string
  }) => {
    setError(null)
    try {
      await createPrintProfile(body)
      await refreshProfiles()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create profile')
    }
  }, [refreshProfiles])

  const removeProfile = useCallback(async (profileId: string) => {
    setError(null)
    try {
      await deletePrintProfile(profileId)
      await refreshProfiles()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete profile')
    }
  }, [refreshProfiles])

  return {
    status,
    stls,
    active,
    history,
    profiles,
    loading,
    error,
    clearError: () => setError(null),
    refreshStatus,
    refreshQueue,
    refreshStls,
    addJob,
    cancelJob,
    addProfile,
    removeProfile,
  }
}
