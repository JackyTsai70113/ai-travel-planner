export type OperationalStatus = 'confirmed' | 'estimated' | 'unverified' | 'stale' | 'conflict' | 'unresolved' | 'unknown'

export interface BundleReservation {
  id: string
  day: string
  time: string | null
  name: string | null
  place_id: string
  kind: string
  unresolved?: boolean
  status?: OperationalStatus
  source?: string
  confidence?: string
  freshness?: string
  last_checked_at?: string
  next_recheck_at?: string
  official_url?: string | null
  phone?: string | null
  itinerary_item_id?: string | null
}

export interface OptionalOperationalHubRecord {
  source?: string
  status?: OperationalStatus
  freshness?: string
  last_checked_at?: string
  next_recheck_at?: string
}

export interface BundlePublicOperations {
  lodgings?: OptionalOperationalHubRecord[]
  food?: OptionalOperationalHubRecord[]
  tides?: OptionalOperationalHubRecord[]
}

export interface BundleDayItem {
  id: string
  kind: string
  start_at: string | null
  end_at: string | null
  place_id: string
  notes?: string
  status?: string | null
  optional?: boolean | null
  fixed?: boolean | null
  cancelable?: boolean | null
  unresolved?: boolean | null
  expected_stay_minutes?: number | null
  transfer_minutes?: number | null
  buffer_minutes?: number | null
}

export interface BundlePlace {
  id: string
  name?: string | null
  address?: string | null
  kind?: string | null
  maps_query?: string | null
  name_ja?: string | null
  phone?: string | null
  official_url?: string | null
}

export interface BundleDay {
  date: string
  summary: string
  items: BundleDayItem[]
}

export interface Constraint {
  id: string
  description: string
}

export interface Bundle {
  trip_id: string
  title: string
  status: 'ok' | 'warning' | 'error'
  local_timezone: string
  places?: BundlePlace[]
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
  operations?: BundlePublicOperations
  days: BundleDay[]
  alternatives?: Array<{
    id: string
    title: string
    plan?: 'A' | 'B' | 'C' | string | null
    status?: string | null
    trigger?: string | null
    tradeoff?: string | null
    summary?: string | null
    decision_gate?: string | null
  }> | null
  overview?: { critical_unknown_count?: number | null } | null
  reservations: BundleReservation[]
  preferences: {
    hard_constraints: Constraint[]
    soft_preferences: Constraint[]
  }
  budget: {
    currency: string
    total: { amount: number; currency: string }
    categories: Record<string, { amount: number; currency: string }>
  }
  validation: { code: string; message: string; severity: string }[]
  meta: {
    generated_at: string
  }
}

export type BundleValidationResult =
  | { ok: true; value: Bundle }
  | { ok: false; error: string }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

export function validateBundle(value: unknown): value is Bundle {
  if (!isRecord(value)) return false
  if (!isString(value.trip_id) || !value.trip_id.trim() || !isString(value.title) || !value.title.trim()) return false
  if (!['ok', 'warning', 'error'].includes(String(value.status))) return false
  if (!isString(value.local_timezone)) return false
  if (!isRecord(value.date_range) || !isString(value.date_range.start_date) || !isString(value.date_range.end_date)) return false
  if (!Array.isArray(value.days) || !value.days.every((day) => isRecord(day) && isString(day.date) && isString(day.summary) && Array.isArray(day.items))) return false
  if (!Array.isArray(value.reservations) || !Array.isArray(value.validation)) return false
  if (!isRecord(value.budget) || !isRecord(value.budget.total) || !isString(value.budget.currency)) return false
  if (!isRecord(value.meta) || !isString(value.meta.generated_at)) return false
  return true
}

export function parseBundle(value: unknown): BundleValidationResult {
  return validateBundle(value)
    ? { ok: true, value }
    : { ok: false, error: '行程資料缺少必要欄位或 schema 不相容。' }
}

export interface ChecklistState {
  [key: string]: boolean
}

export const DEFAULT_CHECKLIST: ChecklistState = {
  passport: true,
  twn_license: true,
  insurance: false,
  itinerary_print: false,
  cash_change: false,
  child_supplies: false,
  elder_med: false,
  heat_rain: false,
  car_docs: false,
  stroller: false,
  first_aid: false,
}

export function safeParseJson<T>(value: string | null, fallback: T): T {
  if (!value) return fallback
  try {
    return JSON.parse(value) as T
  } catch {
    return fallback
  }
}

export function formatMoney(value: { amount: number; currency: string } | null): string {
  if (!value) return '--'
  return `${value.currency} ${value.amount.toLocaleString()}`
}

export function buildMapsLink(placeLabel: string): string {
  const query = encodeURIComponent(placeLabel.trim())
  return `https://www.google.com/maps/search/?api=1&query=${query}`
}

export function findPlaceLabel(places: BundlePlace[] = [], placeId: string): string {
  const found = places.find((place) => place.id === placeId)
  if (!found) return placeId
  return found.name || found.maps_query || placeId
}

export function findPlaceAddress(places: BundlePlace[] = [], placeId: string): string {
  const found = places.find((place) => place.id === placeId)
  return found?.address || ''
}

export function toFriendlyStatus(status: Bundle['status']): string {
  if (status === 'ok') return '可執行'
  if (status === 'warning') return '待補資訊'
  return '嚴重訊息'
}

export function mapStatusClass(status: Bundle['status']): string {
  if (status === 'ok') return 'status ok'
  if (status === 'warning') return 'status warning'
  return 'status error'
}

export function operationalStatusLabel(status: OperationalStatus | undefined | null): string {
  if (status === 'confirmed') return '已確認'
  if (status === 'estimated') return '估計'
  if (status === 'unverified') return '未驗證'
  if (status === 'stale') return '已過時'
  if (status === 'conflict') return '衝突'
  if (status === 'unresolved') return '未補齊'
  return '待補'
}

export function operationalStatusClass(status: OperationalStatus | undefined | null): string {
  if (status === 'confirmed') return 'hub-status confirmed'
  if (status === 'estimated' || status === 'unverified') return 'hub-status estimated'
  if (status === 'stale') return 'hub-status stale'
  if (status === 'conflict') return 'hub-status conflict'
  if (status === 'unresolved') return 'hub-status unresolved'
  return 'hub-status unknown'
}
