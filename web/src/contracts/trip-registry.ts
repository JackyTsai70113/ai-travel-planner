export type TripPublicationStatus = 'published' | 'preview' | 'archived'

export type TripReadiness = 'ready' | 'incomplete' | 'blocked'

type CoverKind = 'image' | 'gradient'

export interface TripCoverMedia {
  kind: CoverKind
  url?: string
  gradient?: string
  alt?: string
  fallback?: string
}

export interface TripRegistryEntry {
  slug: string
  canonical_url: string
  title: string
  short_title: string
  destination_regions: string[]
  date_range: {
    start_date: string
    end_date: string
  }
  duration_days: number
  travelers_summary: string
  theme_id: string
  status: TripPublicationStatus
  readiness: TripReadiness
  last_generated: string
  last_verified: string
  tags: string[]
  cover_media: TripCoverMedia
  hero_summary: string
  key_messages: string[]
  critical_alert_count: number
  bundle_source_slug?: string
}

export type TripCatalogEntry = TripRegistryEntry

export interface TripRegistrySections {
  featured: TripCatalogEntry[]
  upcoming: TripCatalogEntry[]
  archived: TripCatalogEntry[]
  preview: TripCatalogEntry[]
}

export const fallbackRegistry: TripCatalogEntry[] = []

export function isCatalogEntry(value: unknown): value is TripCatalogEntry {
  if (!value || typeof value !== 'object') return false
  const current = value as TripRegistryEntry
  if (typeof current.slug !== 'string' || !current.slug.trim()) return false
  if (typeof current.title !== 'string' || !current.title.trim()) return false
  if (!Array.isArray(current.destination_regions) || !current.destination_regions.every((region) => typeof region === 'string')) return false
  if (!Array.isArray(current.tags) || !current.tags.every((tag) => typeof tag === 'string')) return false
  if (!['published', 'preview', 'archived'].includes(current.status)) return false
  if (!['ready', 'incomplete', 'blocked'].includes(current.readiness)) return false
  if (!current.date_range || typeof current.date_range.start_date !== 'string' || typeof current.date_range.end_date !== 'string') return false
  if (!current.cover_media || (current.cover_media.kind !== 'image' && current.cover_media.kind !== 'gradient')) return false
  return true
}

export function formatDateRange(entry: { date_range: { start_date: string; end_date: string } }): string {
  if (!entry.date_range.start_date || !entry.date_range.end_date) return '待補'
  return `${entry.date_range.start_date} ~ ${entry.date_range.end_date}`
}

export function buildCatalogSections(catalog: TripCatalogEntry[]): TripRegistrySections {
  const now = new Date().toISOString().slice(0, 10)
  const published = catalog.filter((item) => item.status === 'published')
  const preview = catalog.filter((item) => item.status === 'preview')
  const archived = catalog.filter((item) => item.status === 'archived')
  const upcoming = published.filter((item) => item.date_range.end_date >= now)
  const featured = published.filter((item) => item.status === 'published').slice(0, 1)

  return {
    featured,
    upcoming: upcoming.filter((item) => !featured.some((entry) => entry.slug === item.slug)),
    archived,
    preview,
  }
}
