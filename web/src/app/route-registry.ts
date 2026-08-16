export type SectionId =
  | 'overview'
  | 'today'
  | 'map'
  | 'reservation'
  | 'tides'
  | 'food'
  | 'lodging'
  | 'handbook'
  | 'packing'
  | 'budget'
  | 'japanese'
  | 'sources'

export interface SectionDefinition {
  id: SectionId
  label: string
  description: string
  dayScoped?: boolean
  quick?: boolean
}

export const SECTION_DEFINITIONS: SectionDefinition[] = [
  { id: 'overview', label: '旅行總覽', description: 'trip overview', quick: true },
  { id: 'today', label: '每日行程', description: '今天應看哪些行程', dayScoped: true, quick: true },
  { id: 'map', label: '地圖與自駕', description: '地圖與交通狀態', quick: true },
  { id: 'reservation', label: '預約與票券', description: '確認既有預約', quick: true },
  { id: 'tides', label: '潮汐與動態', description: '潮汐與可變條件', dayScoped: true },
  { id: 'food', label: '餐飲與補給', description: '飲食與補給與替代方案' },
  { id: 'lodging', label: '住宿', description: '住宿安排與備註' },
  { id: 'handbook', label: '旅行手冊', description: '緊急與重要行前資訊' },
  { id: 'packing', label: '行李與備忘', description: '行前項目與本機備註' },
  { id: 'budget', label: '行李與預算', description: '預算與費用紀錄' },
  { id: 'japanese', label: '實用日文', description: '實用句型與緊急用語' },
  { id: 'sources', label: '資料來源', description: '內容來源與更新狀態' },
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
