import { useCallback, useEffect, useState } from 'react'
import {
  captureBackground,
  fetchBackgroundStatus,
  scanCapture,
  fetchLibrary,
  patchScanObject,
  deleteScanObject,
  type ScanObject,
  type BackgroundStatus,
} from '../api/client'

export type { ScanObject, BackgroundStatus }

export function useScanner() {
  const [bgStatus, setBgStatus]           = useState<BackgroundStatus>({ captured: false, captured_at: null })
  const [bgCapturing, setBgCapturing]     = useState(false)
  const [scanning, setScanning]           = useState(false)
  const [lastScan, setLastScan]           = useState<ScanObject | null>(null)
  const [library, setLibrary]             = useState<Omit<ScanObject, 'thumbnail_b64'>[]>([])
  const [libraryLoading, setLibraryLoading] = useState(false)
  const [error, setError]                 = useState<string | null>(null)

  const refreshBgStatus = useCallback(async () => {
    try {
      setBgStatus(await fetchBackgroundStatus())
    } catch {
      // non-fatal
    }
  }, [])

  const refreshLibrary = useCallback(async () => {
    setLibraryLoading(true)
    try {
      const r = await fetchLibrary()
      setLibrary(r.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load library')
    } finally {
      setLibraryLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshBgStatus()
    refreshLibrary()
    const id = setInterval(refreshBgStatus, 10_000)
    return () => clearInterval(id)
  }, [refreshBgStatus, refreshLibrary])

  const captureBackgroundFrame = useCallback(async () => {
    setBgCapturing(true)
    setError(null)
    try {
      await captureBackground()
      await refreshBgStatus()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Background capture failed')
    } finally {
      setBgCapturing(false)
    }
  }, [refreshBgStatus])

  const scan = useCallback(async () => {
    setScanning(true)
    setError(null)
    try {
      const result = await scanCapture()
      setLastScan(result)
      await refreshLibrary()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scan failed')
    } finally {
      setScanning(false)
    }
  }, [refreshLibrary])

  const togglePin = useCallback(async (id: string, pinned: boolean) => {
    setError(null)
    try {
      await patchScanObject(id, { pinned })
      await refreshLibrary()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    }
  }, [refreshLibrary])

  const updateHeight = useCallback(async (id: string, height_mm: number) => {
    setError(null)
    try {
      const updated = await patchScanObject(id, { height_mm })
      if (lastScan?.id === id) setLastScan(prev => prev ? { ...prev, height_mm: updated.height_mm } : prev)
      await refreshLibrary()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    }
  }, [lastScan, refreshLibrary])

  const deleteItem = useCallback(async (id: string) => {
    setError(null)
    try {
      await deleteScanObject(id)
      if (lastScan?.id === id) setLastScan(null)
      await refreshLibrary()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    }
  }, [lastScan, refreshLibrary])

  return {
    bgStatus,
    bgCapturing,
    captureBackgroundFrame,
    scanning,
    lastScan,
    scan,
    library,
    libraryLoading,
    refreshLibrary,
    togglePin,
    updateHeight,
    deleteItem,
    error,
    clearError: () => setError(null),
  }
}
