import { useEffect, useMemo, useState } from 'react'
import HomePage from '../pages/HomePage'
import TripApp from './TripApp'
import type { TripCatalogEntry, TripRegistrySections } from '../contracts/trip-registry'
import { buildCatalogSections, isCatalogEntry } from '../contracts/trip-registry'

export interface SiteRoute {
  kind: 'home' | 'trip' | 'not-found'
  slug?: string
}

export function parseSiteRoute(pathname: string): SiteRoute {
  const segments = pathname.split('/').filter(Boolean)
  const tripsIndex = segments.indexOf('trips')
  if (tripsIndex < 0) return { kind: 'home' }
  const slug = segments[tripsIndex + 1]
  return slug ? { kind: 'trip', slug } : { kind: 'not-found' }
}

export function siteRootUrl(currentUrl = window.location.href): URL {
  const url = new URL(currentUrl)
  const segments = url.pathname.split('/').filter(Boolean)
  const tripsIndex = segments.indexOf('trips')
  if (tripsIndex >= 0) {
    url.pathname = `/${segments.slice(0, tripsIndex).join('/')}${segments.slice(0, tripsIndex).length ? '/' : ''}`
  } else if (!url.pathname.endsWith('/')) {
    url.pathname = `${url.pathname}/`
  }
  url.search = ''
  url.hash = ''
  return url
}

export function tripUrl(slug: string, currentUrl = window.location.href): string {
  return new URL(`trips/${encodeURIComponent(slug)}/`, siteRootUrl(currentUrl)).toString()
}

export function setPageMetadata(input: { title: string; description: string; canonical: string }): void {
  document.title = input.title
  const setMeta = (name: string, content: string, property = false) => {
    const selector = property ? `meta[property="${name}"]` : `meta[name="${name}"]`
    let element = document.head.querySelector<HTMLMetaElement>(selector)
    if (!element) {
      element = document.createElement('meta')
      if (property) element.setAttribute('property', name)
      else element.name = name
      document.head.appendChild(element)
    }
    element.content = content
  }
  setMeta('description', input.description)
  setMeta('og:title', input.title, true)
  setMeta('og:description', input.description, true)
  setMeta('og:type', 'website', true)
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'canonical'
    document.head.appendChild(link)
  }
  link.href = input.canonical
}

function RegistryError({ message }: { message: string }) {
  return <main className="portal-state card"><h1>旅行入口暫時無法載入</h1><p>{message}</p></main>
}

export default function SiteRouter() {
  const route = useMemo(() => parseSiteRoute(window.location.pathname), [])
  const [catalog, setCatalog] = useState<TripCatalogEntry[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const registryUrl = new URL('trip-registry.json', window.location.href)
    fetch(registryUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`registry HTTP ${response.status}`)
        return response.json() as Promise<unknown>
      })
      .then((value) => {
        if (!Array.isArray(value) || !value.every(isCatalogEntry)) throw new Error('registry schema 不相容')
        setCatalog(value)
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'registry 載入失敗'))
  }, [])

  useEffect(() => {
    if (!catalog) return
    const trip = route.slug ? catalog.find((item) => item.slug === route.slug) : null
    if (route.kind === 'home') {
      setPageMetadata({
        title: 'AI Travel Planner｜日本旅行網站入口',
        description: '探索由 Canonical Trip 驅動、具備可信度狀態與目的地主題的日本旅行網站。',
        canonical: siteRootUrl().toString(),
      })
    } else if (trip) {
      setPageMetadata({
        title: `${trip.title}｜AI Travel Planner`,
        description: trip.hero_summary,
        canonical: tripUrl(trip.slug),
      })
    }
  }, [catalog, route.kind, route.slug])

  if (error) return <RegistryError message={error} />
  if (!catalog) return <main className="portal-state card"><h1>AI Travel Planner</h1><p>正在載入旅行入口…</p></main>

  if (route.kind === 'trip') {
    const trip = catalog.find((item) => item.slug === route.slug)
    if (!trip) return <RegistryError message="找不到這趟旅行，請從入口重新選擇。" />
    return <TripApp tripMeta={trip} tripSlug={trip.slug} />
  }

  const sections: TripRegistrySections = buildCatalogSections(catalog)
  return (
    <HomePage
      catalog={catalog}
      sections={sections}
      setRoute={({ slug }) => { if (slug) window.location.assign(tripUrl(slug)) }}
      searchPlaceholder="搜尋目的地、旅程或標籤"
    />
  )
}
