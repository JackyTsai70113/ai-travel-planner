import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bundle } from '../contracts/trip'

type LoadStatus = 'loading' | 'ready' | 'error' | 'offline-with-cache' | 'offline-without-cache'

interface BundleLoaderState {
  bundle: Bundle | null
  status: LoadStatus
  error: string
  isOnline: boolean
  isUpdateAvailable: boolean
}

const STORAGE_KEYS = {
  remoteVersion: 'golden_trip_remote_version',
}

export function useBundleLoader(): BundleLoaderState {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [status, setStatus] = useState<LoadStatus>('loading')
  const [error, setError] = useState('')
  const [isOnline, setIsOnline] = useState(true)
  const [isUpdateAvailable, setIsUpdateAvailable] = useState(false)

  const candidates = useMemo(() => {
    const baseUrl = String(import.meta.env.BASE_URL || '/')
    const safeBase = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
    const pathname = window.location.pathname || '/'
    const normalizedPath = pathname.startsWith(safeBase) ? pathname.slice(safeBase.length - 1) : pathname
    const segments = normalizedPath.split('/').filter(Boolean)
    const tripsIndex = segments.indexOf('trips')
    const tripSlug = tripsIndex >= 0 ? segments[tripsIndex + 1] : ''
    const tripBundlePath = tripSlug ? `${safeBase}trips/${tripSlug}/public-bundle.json` : ''
    const localTripBundlePath = tripSlug ? `./trips/${tripSlug}/public-bundle.json` : ''

    return [
      `${safeBase}public-bundle.json`,
      tripBundlePath,
      './public-bundle.json',
      localTripBundlePath,
    ].filter(Boolean)
  }, [])

  const checkVersion = useCallback((data: Bundle) => {
    const remoteGenerated = data.meta?.generated_at
    if (!remoteGenerated) return
    const remoteStored = localStorage.getItem(STORAGE_KEYS.remoteVersion)
    if (remoteStored && remoteStored !== remoteGenerated) {
      setIsUpdateAvailable(true)
    }
    localStorage.setItem(STORAGE_KEYS.remoteVersion, remoteGenerated)
  }, [])

  const load = useCallback(async () => {
    setStatus('loading')
    setError('')
    const attemptLogs: string[] = []
    let response: Response | null = null
    let usedUrl = ''

    for (const url of candidates) {
      try {
        const result = await fetch(url)
        if (!result.ok) {
          attemptLogs.push(`${url} => HTTP ${result.status}`)
          continue
        }
        response = result
        usedUrl = url
        break
      } catch {
        attemptLogs.push(`${url} => network error`)
      }
    }

    if (!response) {
      const hasCache = !!bundle
      const message =
        (hasCache ? '目前為離線快取資料' : '載入不到行程資料') +
        `（已嘗試 ${attemptLogs.join('；')}）`
      setError(message)
      setStatus(hasCache ? 'offline-with-cache' : 'offline-without-cache')
      return
    }

    try {
      const data = (await response.json()) as Bundle
      setBundle(data)
      setIsUpdateAvailable(false)
      checkVersion(data)
      setStatus('ready')
      const isCached = !response.url || response.url.includes('cache') || usedUrl.includes('public')
      if (response.type !== 'basic' && !isCached) {
        setStatus('ready')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '資料格式錯誤')
      setStatus('error')
    }
  }, [bundle, checkVersion, candidates])

  useEffect(() => {
    setIsOnline(window.navigator.onLine)
    const handleOnline = () => {
      setIsOnline(true)
    }
    const handleOffline = () => {
      setIsOnline(false)
    }

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    load()

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [load])

  return {
    bundle,
    status,
    error,
    isOnline,
    isUpdateAvailable: isOnline ? isUpdateAvailable : false,
  }
}
