import { useCallback, useEffect, useRef, useState } from 'react'
import { Bundle, parseBundle } from '../contracts/trip'

type LoadStatus = 'loading' | 'ready' | 'error' | 'offline-with-cache' | 'offline-without-cache'

interface BundleLoaderState {
  bundle: Bundle | null
  status: LoadStatus
  error: string
  isOnline: boolean
  isUpdateAvailable: boolean
}

const STORAGE_KEYS = { remoteVersion: 'trip:active:bundle-version:v1' }

export function resolveBundleUrl(baseUrl: string, canonicalUrl: string): string {
  const base = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
  const path = canonicalUrl.replace(/^\/+/, '').replace(/\/+$/, '')
  return new URL(`${path}/public-bundle.json`, new URL(base, window.location.origin)).toString()
}

export function useBundleLoader(): BundleLoaderState {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const bundleRef = useRef<Bundle | null>(null)
  const [status, setStatus] = useState<LoadStatus>('loading')
  const [error, setError] = useState('')
  const [isOnline, setIsOnline] = useState(true)
  const [isUpdateAvailable, setIsUpdateAvailable] = useState(false)

  const baseUrl = String(import.meta.env.BASE_URL || '/')

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
    let response: Response
    try {
      const base = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
      const registryResponse = await fetch(new URL('trip-registry.json', new URL(base, window.location.origin)))
      if (!registryResponse.ok) throw new Error(`registry HTTP ${registryResponse.status}`)
      const registry = await registryResponse.json() as unknown
      const entry = Array.isArray(registry) && registry[0] && typeof registry[0] === 'object' ? registry[0] as { canonical_url?: unknown } : null
      if (!entry || typeof entry.canonical_url !== 'string') throw new Error('registry schema 不相容')
      response = await fetch(resolveBundleUrl(baseUrl, entry.canonical_url))
      if (!response.ok) throw new Error(`bundle HTTP ${response.status}`)
    } catch (error) {
      const hasCache = !!bundleRef.current
      const message = `${hasCache ? '目前為離線快取資料' : '載入不到行程資料'}（${error instanceof Error ? error.message : 'network error'}）`
      setError(message)
      setStatus(hasCache ? 'offline-with-cache' : 'offline-without-cache')
      return
    }

    try {
      const parsed = parseBundle(await response.json())
      if (!parsed.ok) throw new Error(parsed.error)
      const data = parsed.value
      bundleRef.current = data
      setBundle(data)
      setIsUpdateAvailable(false)
      checkVersion(data)
      setStatus('ready')
    } catch (err) {
      setError(err instanceof Error ? err.message : '資料格式錯誤')
      setStatus('error')
    }
  }, [baseUrl, checkVersion])

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
