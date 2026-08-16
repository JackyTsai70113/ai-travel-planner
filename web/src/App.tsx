import { useEffect, useMemo, useState } from 'react'
import HomePage from './pages/HomePage'
import TripOverviewPage from './pages/TripOverviewPage'
import {
  buildCatalogSections,
  formatDateRange,
  type PublicTripBundle,
  type TripCatalogEntry,
  isCatalogEntry,
  fallbackRegistry,
} from './contracts/trip-registry'

import './styles.css'

type SwUiStatus = 'unknown' | 'registering' | 'ready' | 'failed' | 'unsupported'
interface SwUiState { status: SwUiStatus; message: string }

export const SW_STATUS_KEY = 'trip_portal_sw_status'

type RouteState = { route: 'home' | 'trip'; slug?: string }

type SwBundleMessage = {
  type: 'awaji-cache-update' | 'awaji-sync'
  state?: string
  version?: string
  previousVersion?: string
  message?: string
}

function safeString(value: string | null | undefined, fallback = ''): string {
  return (value || '').toString().trim() || fallback
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function resolveCanonicalPath(basePath: string, state: RouteState): string {
  if (state.route === 'trip' && state.slug) {
    return `${basePath}trips/${state.slug}/`
  }
  return basePath
}

function resolveRouteFromLocation(basePath: string): RouteState {
  const pathname = window.location.pathname
  const normalizedBase = basePath.endsWith('/') ? basePath : `${basePath}/`
  const raw = pathname.startsWith(normalizedBase) ? pathname.slice(normalizedBase.length) : pathname
  const trimmed = raw.replace(/^\/+|\/+$/g, '')
  const query = new URLSearchParams(window.location.search)
  const tripFromQuery = query.get('trip')

  if (query.has('route')) {
    const routeParam = safeDecode(safeString(query.get('route')))
    const normalizedRoute = routeParam.startsWith('/') ? routeParam.slice(1) : routeParam
    if (normalizedRoute.startsWith('trips/')) {
      const slug = normalizedRoute.replace(/^trips\//, '').split('/')[0]
      if (slug) return { route: 'trip', slug }
    }
  }
  if (tripFromQuery) return { route: 'trip', slug: tripFromQuery }
  if (trimmed.startsWith('trips/')) {
    const slug = trimmed.replace(/^trips\//, '').split('/')[0]
    return { route: 'trip', slug }
  }
  return { route: 'home' }
}

function pushRoute(state: RouteState, basePath: string): void {
  const url = new URL(resolveCanonicalPath(basePath, state), window.location.origin)
  window.history.pushState({}, '', `${url.pathname}${url.search}`)
  window.dispatchEvent(new PopStateEvent('trip-route'))
}

function setMeta({ title, description, canonical }: { title: string; description: string; canonical: string }) {
  document.title = title
  const ensureMeta = (selector: string, attr: 'name' | 'property', key: string, value: string) => {
    if (!value) return
    let meta = document.querySelector<HTMLMetaElement>(selector)
    if (!meta) {
      meta = document.createElement('meta')
      meta.setAttribute(attr, key)
      document.head.appendChild(meta)
    }
    meta.setAttribute('content', value)
  }
  ensureMeta('meta[name="description"]', 'name', 'description', description)
  ensureMeta('meta[property="og:title"]', 'property', 'og:title', title)
  ensureMeta('meta[property="og:description"]', 'property', 'og:description', description)
  ensureMeta('meta[property="og:url"]', 'property', 'og:url', canonical)
  ensureMeta('meta[name="twitter:card"]', 'name', 'twitter:card', 'summary_large_image')
  ensureMeta('meta[name="theme-color"]', 'name', 'theme-color', '#0f172a')
  let link = document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'canonical'
    document.head.appendChild(link)
  }
  link.href = canonical
}

function parseBundle(url: string): Promise<PublicTripBundle | null> {
  return fetch(url, { cache: 'no-store' })
    .then((response) => {
      if (!response.ok) throw new Error(`bundle-fetch-${response.status}`)
      return response.json()
    })
    .then((payload) => {
      return payload as PublicTripBundle
    })
    .catch(() => null)
}

export default function App() {
  const basePath = useMemo(() => String(import.meta.env.BASE_URL || '/'), [])
  const [route, setRoute] = useState<RouteState>(() => resolveRouteFromLocation(basePath))
  const [catalog, setCatalog] = useState<TripCatalogEntry[]>(fallbackRegistry)
  const [bundleMap, setBundleMap] = useState<Record<string, PublicTripBundle | null>>({})
  const [swStatus, setSwStatus] = useState<SwUiState>({ status: 'unknown', message: '' })

  const catalogLookup = useMemo(() => {
    const map: Record<string, TripCatalogEntry> = {}
    catalog.forEach((entry) => {
      map[entry.slug] = entry
    })
    return map
  }, [catalog])

  const sections = useMemo(() => buildCatalogSections(catalog), [catalog])
  const selectedTrip = route.route === 'trip' && route.slug ? catalogLookup[route.slug] || null : null

  useEffect(() => {
    const loadCatalog = async () => {
      const registryPath = `${basePath}trip-registry.json`
      try {
        const response = await fetch(registryPath, { cache: 'no-store' })
        if (!response.ok) return
        const payload = await response.json()
        if (!Array.isArray(payload)) return
        const typed = payload.filter(isCatalogEntry)
        if (typed.length > 0) {
          setCatalog(typed)
        }
      } catch {
        // keep fallback
      }
    }
    loadCatalog()
  }, [basePath])

  useEffect(() => {
    const onPop = () => setRoute(resolveRouteFromLocation(basePath))
    window.addEventListener('popstate', onPop)
    window.addEventListener('trip-route', onPop)
    return () => {
      window.removeEventListener('popstate', onPop)
      window.removeEventListener('trip-route', onPop)
    }
  }, [basePath])

  useEffect(() => {
    const stored = safeString(localStorage.getItem(SW_STATUS_KEY))
    try {
      if (stored) {
        setSwStatus(JSON.parse(stored) as SwUiState)
      }
    } catch {
      // no-op
    }

    const onAwaji = (event: Event) => {
      const customEvent = event as CustomEvent<SwUiState>
      const detail = customEvent.detail
      if (!detail?.status) return
      setSwStatus(detail)
      localStorage.setItem(SW_STATUS_KEY, JSON.stringify(detail))
    }
    const onSwMessage = (event: MessageEvent<SwBundleMessage>) => {
      const detail = event.data
      if (!detail || typeof detail !== 'object') return
      if (detail.type === 'awaji-cache-update') {
        setSwStatus((current) => ({
          ...current,
          message: `行程快取更新：${detail.previousVersion || 'unknown'} → ${detail.version || 'unknown'}`,
        }))
      }
      if (detail.type === 'awaji-sync' && detail.state === 'bundle_offline') {
        setSwStatus((current) => ({
          ...current,
          message: `行程快取目前離線：${detail.version || '僅離線快取可用'}`,
        }))
      }
      if (detail.type === 'awaji-sync' && detail.state === 'bundle_synced') {
        setSwStatus((current) => ({
          ...current,
          message: `行程快取已同步：${detail.version || '完成'}`,
        }))
      }
    }

    window.addEventListener('awaji-sw-status', onAwaji as EventListener)
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('message', onSwMessage as EventListener)
    }
    return () => {
      window.removeEventListener('awaji-sw-status', onAwaji as EventListener)
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.removeEventListener('message', onSwMessage as EventListener)
      }
    }
  }, [])

  useEffect(() => {
    const base = new URL(resolveCanonicalPath(basePath, route), window.location.origin)
    const isHome = route.route === 'home'
    const selected = selectedTrip || null
    setMeta({
      title: isHome
        ? 'AI Travel Planner ｜ Trip Catalog'
        : selected ? `${selected.title}｜Trip Landing` : 'Trip Landing',
      description: isHome
        ? 'AI Travel Planner 入口：多旅程列表，一鍵進入精選行程' : selected
          ? `${selected.title}（${formatDateRange(selected)}）：${selected.hero_summary}`
          : 'Trip 頁面',
      canonical: base.toString(),
    })
  }, [basePath, route.route, route.slug, selectedTrip])

  useEffect(() => {
    if (route.route !== 'trip' || !route.slug) return
    const tripId = route.slug
    parseBundle(`${basePath}trips/${tripId}/public-bundle.json`).then((data) => {
      setBundleMap((prev) => ({ ...prev, [tripId]: data }))
    })
  }, [basePath, route.route, route.slug])

  useEffect(() => {
    if (route.route === 'trip' && route.slug && !catalogLookup[route.slug] && catalog.length > 0) {
      if (catalogLookup['awaji-2026']) {
        const fallbackRoute = { route: 'trip', slug: 'awaji-2026' } as const
        window.history.replaceState({}, '', resolveCanonicalPath(basePath, fallbackRoute))
        setRoute(fallbackRoute)
      }
    }
  }, [catalogLookup, catalog.length, route.route, route.slug, basePath])

  const goRoute = (next: RouteState) => {
    pushRoute(next, basePath)
    setRoute(next)
  }

  const activeBundle = route.slug ? bundleMap[route.slug] || null : null

  return (
    <main className="portal-shell">
      <section className="hero-shell card-shell">
        <p className="eyebrow">AI Travel Planner</p>
        <h1>{route.route === 'home' ? '日本行程作品入口' : selectedTrip?.title || 'Trip Landing'}</h1>
        <p className="muted">一次看到所有已發佈、預覽與封存 trip，支援一鍵進入分享與重新檢視。</p>
      </section>

      {route.route === 'home' && (
        <HomePage
          catalog={catalog}
          sections={sections}
          setRoute={goRoute}
          searchPlaceholder="搜尋目的地、主題、標籤..."
        />
      )}

      <TripOverviewPage
        route={route}
        setRoute={goRoute}
        trip={selectedTrip}
        bundle={activeBundle}
        swStatus={swStatus}
      />

      <section className="card-shell trust-row">
        <h2>資料可信度</h2>
        <ul>
          <li>preview / blocked 會以明確標籤顯示，避免誤導為可安心出發。</li>
          <li>行程資訊來源為 public bundle 與公開 registry，且不含私有預訂憑證。</li>
          <li>最後驗證：{selectedTrip ? selectedTrip.last_verified : '—'}</li>
          <li>快取更新：{swStatus.status === 'ready' ? '正常' : '進行中 / 檢查中'}</li>
        </ul>
      </section>
    </main>
  )
}
