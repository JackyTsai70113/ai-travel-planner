export type SectionId =
  | 'overview'
  | 'today'
  | 'reservation'
  | 'food'
  | 'packing'
  | 'japanese'

export interface SectionDefinition {
  id: SectionId
  label: string
  description: string
  dayScoped?: boolean
  quick?: boolean
}

export const SECTION_DEFINITIONS: SectionDefinition[] = [
  { id: 'overview', label: '旅行總覽', description: '五日重點與住宿安排', quick: true },
  { id: 'today', label: '每日行程', description: '今天應看哪些行程', dayScoped: true, quick: true },
  { id: 'reservation', label: '預約時間', description: '已排定的日期與時間', quick: true },
  { id: 'food', label: '餐飲與補給', description: '餐廳、餐點與補給資訊' },
  { id: 'packing', label: '攜帶物品', description: '清楚列出這趟旅程要帶什麼' },
  { id: 'japanese', label: '實用日文', description: '實用句型與緊急用語' },
]

export const SECTION_BY_ID = new Map<string, SectionDefinition>(SECTION_DEFINITIONS.map((item) => [item.id, item]))

export function isValidSection(section: string | null | undefined): section is SectionId {
  return section ? SECTION_BY_ID.has(section) : false
}

export function parseSection(section: string | undefined, fallbackSection: SectionId): SectionId {
  if (isValidSection(section)) return section
  return fallbackSection
}

export interface TripRoute {
  section: SectionId
  day?: string
  item?: string
  raw: string
}

export function buildRoutePath(route: Partial<TripRoute>): string {
  const safeSection = parseSection(route.section, 'overview')
  const segment: string[] = [safeSection]
  if (route.day) segment.push(encodeURIComponent(route.day))
  if (route.item) segment.push(encodeURIComponent(route.item))
  return `#/${segment.join('/')}`
}

export function parseRouteFromHash(hash: string, fallbackSection: SectionId): TripRoute {
  const normalizedHash = hash.replace(/^#\//, '')
  const segments = normalizedHash.split('/').filter(Boolean)
  const section = parseSection(segments[0], fallbackSection)
  return {
    section,
    day: segments[1] ? decodeURIComponent(segments[1]) : undefined,
    item: segments[2] ? decodeURIComponent(segments[2]) : undefined,
    raw: normalizedHash,
  }
}
