import { useCallback, useEffect, useState } from 'react'
import { Bundle, parseBundle } from '../contracts/trip'

type LoadStatus = 'loading' | 'ready' | 'error'

interface BundleLoaderState {
  bundle: Bundle | null
  status: LoadStatus
  error: string
}

function resolveAppBaseUrl(baseUrl: string, pageUrl: string): URL {
  const base = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
  return new URL(base, pageUrl)
}

export function resolveRegistryUrl(baseUrl: string, pageUrl = window.location.href): string {
  const page = new URL(pageUrl)
  const segments = page.pathname.split('/').filter(Boolean)
  const tripsIndex = segments.indexOf('trips')
  if (tripsIndex >= 0) {
    page.pathname = `/${segments.slice(0, tripsIndex).join('/')}${segments.slice(0, tripsIndex).length ? '/' : ''}`
    page.search = ''
    page.hash = ''
    return new URL('trip-registry.json', page).toString()
  }
  return new URL('trip-registry.json', resolveAppBaseUrl(baseUrl, pageUrl)).toString()
}

export function resolveBundleUrl(baseUrl: string, canonicalUrl: string, pageUrl = window.location.href): string {
  const path = canonicalUrl.replace(/^\/+/, '').replace(/\/+$/, '')
  const appBase = resolveAppBaseUrl(baseUrl, pageUrl)
  const appPath = appBase.pathname.replace(/\/+$/, '')
  if (baseUrl.startsWith('.') && appPath.endsWith(`/${path}`)) {
    return new URL('public-bundle.json', appBase).toString()
  }
  return new URL(`${path}/public-bundle.json`, appBase).toString()
}

export function useBundleLoader(tripSlug?: string): BundleLoaderState {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [status, setStatus] = useState<LoadStatus>('loading')
  const [error, setError] = useState('')

  const baseUrl = String(import.meta.env.BASE_URL || '/')

  const load = useCallback(async () => {
    setStatus('loading')
    setError('')
    let response: Response
    try {
      const registryResponse = await fetch(resolveRegistryUrl(baseUrl))
      if (!registryResponse.ok) throw new Error(`registry HTTP ${registryResponse.status}`)
      const registry = await registryResponse.json() as unknown
      const entries = Array.isArray(registry) ? registry : []
      const entry = entries.find((candidate) => {
        if (!candidate || typeof candidate !== 'object') return false
        return !tripSlug || (candidate as { slug?: unknown }).slug === tripSlug
      }) as { canonical_url?: unknown } | undefined
      if (!entry || typeof entry.canonical_url !== 'string') throw new Error('registry schema 不相容')
      response = await fetch(resolveBundleUrl(baseUrl, entry.canonical_url))
      if (!response.ok) throw new Error(`bundle HTTP ${response.status}`)
    } catch (error) {
      const message = `載入不到行程資料（${error instanceof Error ? error.message : 'network error'}）`
      setError(message)
      setStatus('error')
      return
    }

    try {
      const parsed = parseBundle(await response.json())
      if (!parsed.ok) throw new Error(parsed.error)
      const data = parsed.value
      setBundle(data)
      setStatus('ready')
    } catch (err) {
      setError(err instanceof Error ? err.message : '資料格式錯誤')
      setStatus('error')
    }
  }, [baseUrl, tripSlug])

  useEffect(() => {
    load()
  }, [load])

  return {
    bundle,
    status,
    error,
  }
}
