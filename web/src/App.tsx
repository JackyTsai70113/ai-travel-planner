import { useCallback, useEffect, useMemo, useState } from 'react'
import AppProviders from './app/AppProviders'
import TripApp from './app/TripApp'
import {
  fallbackRegistry,
  type TripCatalogEntry,
  type TripRegistrySections,
  buildCatalogSections,
  isCatalogEntry,
  formatDateRange,
} from './contracts/trip-registry'
import HomePage from './pages/HomePage'

interface SiteRoute {
  route: 'home'
}

interface TripRoute {
  route: 'trip'
  slug: string
}

type RouteState = SiteRoute | TripRoute

interface SiteMeta {
  title: string
  description: string
  canonical: string
  image?: string
}

function setMetaTags({ title, description, canonical, image }: SiteMeta): void {
  if (typeof document === 'undefined') return
  document.title = title

  const ensureMeta = (selector: string, attr: 'name' | 'property', key: string, value: string) => {
    if (!value) return
    const current = document.querySelector<HTMLMetaElement>(selector)
    if (current) {
      current.setAttribute('content', value)
      return
    }
    const next = document.createElement('meta')
    next.setAttribute(attr, key)
    next.setAttribute('content', value)
    document.head.appendChild(next)
  }

  ensureMeta('meta[name="description"]', 'name', 'description', description)
  ensureMeta('meta[property="og:title"]', 'property', 'og:title', title)
  ensureMeta('meta[property="og:description"]', 'property', 'og:description', description)
  ensureMeta('meta[property="og:url"]', 'property', 'og:url', canonical)
  ensureMeta('meta[property="og:image"]', 'property', 'og:image', image || '')
  ensureMeta('meta[name="twitter:card"]', 'name', 'twitter:card', image ? 'summary_large_image' : 'summary')
  ensureMeta('meta[name="twitter:title"]', 'name', 'twitter:title', title)
  ensureMeta('meta[name="twitter:description"]', 'name', 'twitter:description', description)
  ensureMeta('meta[name="twitter:image"]', 'name', 'twitter:image', image || '')
  ensureMeta('meta[name="theme-color"]', 'name', 'theme-color', '#0b2f57')
  let link = document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'canonical'
    document.head.appendChild(link)
  }
  link.href = canonical
}

function resolveBasePath(): string {
  const basePath = new URL(import.meta.env.BASE_URL || '/', window.location.href).pathname
  return basePath.endsWith('/') ? basePath : `${basePath}/`
}

function trimPath(pathname: string, basePath: string): string {
  if (pathname === basePath) return ''
  if (!basePath || basePath === '/') return pathname.replace(/^\/+|\/+$/g, '')
  if (pathname.startsWith(basePath)) {
    return pathname.slice(basePath.length).replace(/^\/+|\/+$/g, '')
  }
  return pathname.replace(/^\/+|\/+$/g, '')
}

function resolveTripRouteFromPath(pathname: string, basePath: string): string | null {
  const normalized = trimPath(pathname, basePath)
  if (!normalized || !normalized.startsWith('trips/')) return null
  const parts = normalized.split('/').filter(Boolean)
  const slug = parts[1]
  if (!slug || !slug.trim()) return null
  return slug
}

function buildRouteUrl(basePath: string, route: RouteState): string {
  if (route.route === 'trip') {
    return `${basePath}trips/${route.slug}/`
  }
  return basePath
}

function resolveRouteFromLocation(basePath: string): RouteState {
  const routeSearch = new URLSearchParams(window.location.search).get('route')
  if (routeSearch) {
    try {
      const parsed = decodeURIComponent(routeSearch)
      const routePath = parsed.startsWith('/') ? parsed : `/${parsed}`
      const fromRoute = resolveTripRouteFromPath(routePath, '/')
      if (fromRoute) return { route: 'trip', slug: fromRoute }
    } catch {
      // ignore malformed route param
    }
  }

  const fromPath = resolveTripRouteFromPath(window.location.pathname, basePath)
  if (fromPath) return { route: 'trip', slug: fromPath }
  return { route: 'home' }
}

function ensureCanonicalPath(basePath: string, nextRoute: RouteState): boolean {
  const expected = buildRouteUrl(basePath, nextRoute)
  if (window.location.pathname === expected) return false
  window.history.replaceState({}, '', expected)
  return true
}

function buildCanonical(basePath: string, route: RouteState): string {
  return `${window.location.origin}${buildRouteUrl(basePath, route)}`
}

export default function App() {
  const basePath = useMemo(() => resolveBasePath(), [])
  const [route, setRouteState] = useState<RouteState>(() => resolveRouteFromLocation(basePath))
  const [catalog, setCatalog] = useState<TripCatalogEntry[]>(fallbackRegistry)
  const [sections, setSections] = useState<TripRegistrySections>(() => buildCatalogSections(fallbackRegistry))

  const catalogLookup = useMemo<Record<string, TripCatalogEntry>>(() => {
    const next: Record<string, TripCatalogEntry> = {}
    catalog.forEach((item) => {
      next[item.slug] = item
    })
    return next
  }, [catalog])

  const selectedTrip = route.route === 'trip' ? catalogLookup[route.slug] : null
  const fallbackTrip = sections.featured[0] || sections.upcoming[0] || sections.preview[0]

  const syncMeta = useCallback(
    (next: RouteState) => {
      const currentTrip = next.route === 'trip' ? catalogLookup[next.slug] : null
      const source = currentTrip || fallbackTrip || fallbackRegistry[0]
      const title =
        next.route === 'home'
          ? 'AI Travel Planner | 日本行程作品入口'
          : `${(currentTrip?.title || 'Trip Landing')} | AI Travel Planner`
      const description =
        next.route === 'home'
          ? 'AI Travel Planner 入口，展示已發布與預覽中的日本旅遊作品。'
          : `${currentTrip?.hero_summary || '行程首屏總覽'}（${formatDateRange(source)}）`
      const image =
        currentTrip?.cover_media.kind === 'image'
          ? currentTrip?.cover_media.url
          : currentTrip?.cover_media.fallback
      setMetaTags({
        title,
        description,
        canonical: buildCanonical(basePath, next),
        image,
      })
    },
    [basePath, catalogLookup, fallbackTrip],
  )

  useEffect(() => {
    const loadRegistry = async () => {
      try {
        const response = await fetch(`${basePath}trip-registry.json`, { cache: 'no-store' })
        if (!response.ok) return
        const payload = await response.json()
        if (!Array.isArray(payload)) return
        const typed = payload.filter(isCatalogEntry)
        if (!typed.length) return
        setCatalog(typed)
        setSections(buildCatalogSections(typed))
      } catch {
        // Keep fallbackRegistry.
      }
    }
    loadRegistry()
  }, [basePath])

  useEffect(() => {
    const onPop = () => setRouteState(resolveRouteFromLocation(basePath))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [basePath])

  useEffect(() => {
    syncMeta(route)
    ensureCanonicalPath(basePath, route)
  }, [route, syncMeta, basePath])

  useEffect(() => {
    if (route.route !== 'trip' || catalog.length === 0) return
    if (selectedTrip) return

    const fallback = fallbackTrip || fallbackRegistry[0]
    if (!fallback) return
    const next: RouteState = fallback.slug ? { route: 'trip', slug: fallback.slug } : { route: 'home' }
    if (next.route === 'trip' && route.route === 'trip' && route.slug === next.slug) return
    if (next.route === 'trip') {
      window.history.replaceState({}, '', buildRouteUrl(basePath, next))
      setRouteState(next)
    }
  }, [catalog.length, fallbackTrip, route, selectedTrip, basePath])

  const goRoute = (next: { route: 'home' | 'trip'; slug?: string }): void => {
    const resolved: RouteState =
      next.route === 'home'
        ? { route: 'home' }
        : { route: 'trip', slug: next.slug || sections.featured[0]?.slug || 'awaji-2026' }

    const nextPath = buildRouteUrl(basePath, resolved)
    const current = `${window.location.pathname}${window.location.search}`
    if (current !== nextPath) {
      window.history.pushState({}, '', nextPath)
    }
    setRouteState(resolved)
  }

  return (
    <AppProviders>
      {route.route === 'home' ? (
        <main className="portal-shell">
          <section className="portal-hero">
            <p className="portal-eyebrow">AI Travel Planner</p>
            <h1>日本行程作品入口</h1>
            <p className="muted">一眼看見所有可瀏覽的日本行程，並直接進入精選 trip landing。</p>
            <button type="button" className="primary-action" onClick={() => goRoute({ route: 'trip', slug: 'awaji-2026' })}>
              一鍵進入 Awaji 2026
            </button>
          </section>
          <HomePage
            catalog={catalog}
            sections={sections}
            setRoute={goRoute}
            searchPlaceholder="搜尋目的地、年份、主題..."
          />
          <section className="card trust-row">
            <h2>資料可信度說明</h2>
            <ul>
              <li>published / preview / archived 會用顏色與文字明確標示，不會誤導為可直接出發。</li>
              <li>trip landing 僅使用公開 registry 與 public-bundle，不包含私密預約憑證。</li>
              <li>offline 缺資料時仍可閱讀快取版本，並在狀態列顯示重新整理。</li>
            </ul>
          </section>
        </main>
      ) : (
        <TripApp tripMeta={selectedTrip || fallbackTrip || null} />
      )}
    </AppProviders>
  )
}
