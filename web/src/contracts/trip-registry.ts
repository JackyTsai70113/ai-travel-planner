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
  date_range: { start_date: string; end_date: string }
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

export interface PublicTripBundle {
  trip_id: string
  title: string
  status: 'ok' | 'warning' | 'error'
  local_timezone: string
  date_range: { start_date: string; end_date: string }
  traveler_profile: {
    adults: number
    children_count: number
    children_ages: number[]
  }
  selected: {
    hotel_place_ids: string[]
    flight_ids: string[]
  }
  days: {
    date: string
    summary: string
    items: {
      id: string
      kind: string
      start_at: string | null
      end_at: string | null
      place_id: string
      notes: string | null
    }[]
  }[]
  reservations: {
    id: string
    day: string
    time: string | null
    name: string | null
    place_id: string
    kind: string
    unresolved: boolean
  }[]
  preferences: {
    hard_constraints: { id: string; description: string }[]
    soft_preferences: { id: string; description: string }[]
  }
  budget: {
    currency: string
    total: { amount: number; currency: string }
    categories: Record<string, { amount: number; currency: string }>
  }
  validation: { code: string; message: string; severity: 'error' | 'warning' | 'info' }[]
  meta: {
    generated_at: string
    source_path?: string
    source_sha256?: string
    bundle_sha256?: string
    last_checked_at?: string
    next_recheck_at?: string
  }
}

export interface TripCatalogSections {
  featured: TripRegistryEntry[]
  upcoming: TripRegistryEntry[]
  archived: TripRegistryEntry[]
  preview: TripRegistryEntry[]
}

export const fallbackRegistry: TripRegistryEntry[] = [
  {
    slug: 'awaji-2026',
    canonical_url: 'trips/awaji-2026',
    title: '2026 淡路島・鳴門家庭行程',
    short_title: 'Awaji 2026',
    destination_regions: ['淡路島', '鳴門'],
    date_range: { start_date: '2026-08-27', end_date: '2026-08-31' },
    duration_days: 5,
    travelers_summary: '2 位大人 + 1 位小孩',
    theme_id: 'coastal-family',
    status: 'published',
    readiness: 'ready',
    last_generated: '2026-08-10',
    last_verified: '2026-08-15',
    tags: ['自駕', 'family', 'child-friendly', 'elder-friendly'],
    cover_media: {
      kind: 'gradient',
      gradient: 'linear-gradient(130deg, #0c4a6e 0%, #38bdf8 60%, #7dd3fc 100%)',
      fallback: '淡路海岸晨霧與海風',
    },
    hero_summary: '重點資訊',
    key_messages: ['行前資料已補齊，仍保留航班與預約待確認欄位'],
    critical_alert_count: 1,
  },
  {
    slug: 'kansai-preview-2025',
    canonical_url: 'trips/kansai-preview-2025',
    title: '2025 關西自然體驗預錄行程',
    short_title: 'Kansai 2025',
    destination_regions: ['東京', '福岡', '佐賀'],
    date_range: { start_date: '2025-09-21', end_date: '2025-09-25' },
    duration_days: 5,
    travelers_summary: '2 位大人',
    theme_id: 'urban-culture',
    status: 'preview',
    readiness: 'incomplete',
    last_generated: '2025-09-01',
    last_verified: '2025-09-01',
    tags: ['自駕', 'family'],
    cover_media: {
      kind: 'gradient',
      gradient: 'linear-gradient(130deg, #334155 0%, #f59e0b 55%, #fbbf24 100%)',
      fallback: '關西夜景與市街場景',
    },
    hero_summary: '待完善：部分固定預約待核對',
    key_messages: ['未完成預約資訊', '需確認住宿與行程時段'],
    critical_alert_count: 3,
  },
]

export function isCatalogEntry(value: unknown): value is TripRegistryEntry {
  if (!value || typeof value !== 'object') return false
  const typed = value as TripRegistryEntry
  if (typeof typed.slug !== 'string' || typed.slug.trim() === '') return false
  if (typeof typed.title !== 'string' || typed.title.trim() === '') return false
  if (typeof typed.short_title !== 'string' || typed.short_title.trim() === '') return false
  if (!Array.isArray(typed.destination_regions)) return false
  if (!Array.isArray(typed.tags)) return false
  if (!['published', 'preview', 'archived'].includes(typed.status)) return false
  if (!['ready', 'incomplete', 'blocked'].includes(typed.readiness)) return false
  if (!typed.date_range || typeof typed.date_range.start_date !== 'string' || typeof typed.date_range.end_date !== 'string') return false
  if (!typed.cover_media || (typed.cover_media.kind !== 'image' && typed.cover_media.kind !== 'gradient')) return false
  return true
}

export function formatDateRange(entry: { date_range: { start_date: string; end_date: string } }): string {
  if (!entry.date_range.start_date || !entry.date_range.end_date) return '待補'
  return `${entry.date_range.start_date} ~ ${entry.date_range.end_date}`
}

export function buildCatalogSections(catalog: TripRegistryEntry[]): TripCatalogSections {
  const published = catalog.filter((item) => item.status === 'published')
  const preview = catalog.filter((item) => item.status === 'preview')
  const archived = catalog.filter((item) => item.status === 'archived')
  const now = new Date().toISOString().slice(0, 10)
  const upcoming = published.filter((item) => item.date_range.end_date >= now)
  const featured = published[0] ? [published[0]] : []
  return {
    featured,
    upcoming: upcoming.filter((item) => !featured.some((entry) => entry.slug === item.slug)),
    archived,
    preview,
  }
}
