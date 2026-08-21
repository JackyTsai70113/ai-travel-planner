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
}

export type TripCatalogEntry = TripRegistryEntry

export interface TripRegistrySections {
  featured: TripCatalogEntry[]
  upcoming: TripCatalogEntry[]
  archived: TripCatalogEntry[]
  preview: TripCatalogEntry[]
}

export const fallbackRegistry: TripCatalogEntry[] = [
  {
    slug: 'awaji-2026',
    canonical_url: 'trips/awaji-2026',
    title: '2026 淡路島・鳴門家庭行程',
    short_title: 'Awaji 2026',
    destination_regions: ['淡路島', '鳴門'],
    date_range: {
      start_date: '2026-08-27',
      end_date: '2026-08-31',
    },
    duration_days: 5,
    travelers_summary: '2 位大人 + 1 位小孩',
    theme_id: 'setouchi-awaji',
    status: 'published',
    readiness: 'incomplete',
    last_generated: '2026-08-10',
    last_verified: '2026-08-15',
    tags: ['family', 'self-drive', 'child-friendly'],
    cover_media: {
      kind: 'gradient',
      gradient: 'linear-gradient(130deg, #0b4a6f 0%, #2e90dc 55%, #79b8f8 100%)',
      fallback: '淡路海岸晨霧',
    },
    hero_summary: '旅前資料待補，重點已可閱讀首屏。',
    key_messages: ['行程主題與路線已穩定。', '固定預約待核對。'],
    critical_alert_count: 2,
  },
  {
    slug: 'kansai-preview-2025',
    canonical_url: 'trips/kansai-preview-2025',
    title: '2025 關西自然體驗預錄行程',
    short_title: 'Kansai 2025',
    destination_regions: ['大阪', '京都', '神戶'],
    date_range: {
      start_date: '2025-09-21',
      end_date: '2025-09-25',
    },
    duration_days: 5,
    travelers_summary: '2 位大人',
    theme_id: 'generic-japan',
    status: 'preview',
    readiness: 'incomplete',
    last_generated: '2025-09-01',
    last_verified: '2025-09-01',
    tags: ['family', 'self-drive', 'elder-friendly'],
    cover_media: {
      kind: 'gradient',
      gradient: 'linear-gradient(130deg, #334155 0%, #f59e0b 55%, #fbbf24 100%)',
      fallback: '關西山林與城市並存的夜景',
    },
    hero_summary: '預覽版，部份資訊待核對。',
    key_messages: ['未完成預約欄位', '住宿與行程時段仍待補'],
    critical_alert_count: 4,
  },
]

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
