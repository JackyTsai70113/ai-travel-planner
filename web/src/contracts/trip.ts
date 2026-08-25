export type OperationalStatus = 'confirmed' | 'estimated' | 'reported' | 'user-confirmed' | 'warning' | 'error' | 'critical' | 'info' | 'unverified' | 'stale' | 'conflict' | 'unresolved' | 'unknown'

export interface BundleProvenance {
  status?: OperationalStatus | null
  provider?: string | null
  source_ref?: string | null
  source_refs?: string[]
  source_url?: string | null
  retrieved_at?: string | null
  confidence?: number | string | null
  note?: string | null
}

export type BundleFieldProvenance = Record<string, BundleProvenance | null | undefined>

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
  id?: string
  place_id?: string
  source?: string
  status?: OperationalStatus
  freshness?: string
  last_checked_at?: string
  next_recheck_at?: string
}

export interface BundlePretripChecklistItem {
  id: string
  completed?: boolean
  timing?: string | null
  item: string
  action?: string | null
  fallback?: string | null
  contact?: string | null
}

export interface BundlePublicOperations {
  lodgings?: OptionalOperationalHubRecord[]
  food?: OptionalOperationalHubRecord[]
  tides?: OptionalOperationalHubRecord[]
  pretrip_checklist?: BundlePretripChecklistItem[]
  emergency?: unknown[]
  fuel?: Record<string, unknown>
  handbook?: unknown[]
  returns?: unknown[]
  supplies?: unknown[]
}

export interface BundleTideEvent {
  kind: 'high' | 'low'
  time: string
  height_cm: number
}

export interface BundleTideDay {
  date: string
  tide_type: string
  events: BundleTideEvent[]
}

export interface BundleTideConditions {
  status?: OperationalStatus | null
  status_label?: string | null
  summary?: string | null
  provider?: string | null
  source_url?: string | null
  last_checked?: string | null
  recheck_at?: string | null
  station?: string | null
  days?: BundleTideDay[]
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
  transport_leg_id?: string | null
  alternative_place_ids?: string[]
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
  image_url?: string | null
  image_source_url?: string | null
  image_alt?: string | null
  google_maps_url?: string | null
  opening_hours_note?: string | null
  parking?: string | null
  accessibility_notes?: string | null
  status?: OperationalStatus | null
  source_refs?: string[]
  provenance?: BundleProvenance | BundleFieldProvenance | null
  field_provenance?: BundleFieldProvenance | null
}

export interface BundleTransportLeg {
  id: string
  mode: string
  status: OperationalStatus
  from_place: string
  to_place: string
  from_label: string
  to_label: string
  departure_at: string | null
  arrival_at: string | null
  estimated_duration_minutes: number | null
  transfer_minutes?: number | null
  buffer_minutes?: number | null
  note?: string | null
  source_url?: string | null
  google_maps_directions_url?: string | null
  distance_km?: number | null
  source_refs?: string[]
  provenance?: BundleProvenance | null
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
  conditions?: {
    tide?: BundleTideConditions
    weather?: Record<string, unknown>
    closures?: unknown[]
    freshness?: string
  }
  days: BundleDay[]
  transport_legs?: BundleTransportLeg[]
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
  return `https://www.openstreetmap.org/search?query=${query}`
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
  if (status === 'warning') return '有提醒'
  return '嚴重訊息'
}

export function mapStatusClass(status: Bundle['status']): string {
  if (status === 'ok') return 'status ok'
  if (status === 'warning') return 'status warning'
  return 'status error'
}

export function operationalStatusLabel(status: OperationalStatus | undefined | null): string {
  if (status === 'confirmed') return '已確認'
  if (status === 'user-confirmed') return '使用者已確認'
  if (status === 'reported') return '來源已報告'
  if (status === 'estimated') return '估計'
  if (status === 'warning') return '注意'
  if (status === 'error' || status === 'critical') return '有風險'
  if (status === 'info') return '資訊'
  if (status === 'unverified') return '來源資訊'
  if (status === 'stale') return '已過時'
  if (status === 'conflict') return '衝突'
  if (status === 'unresolved') return '需處理'
  return '需處理'
}

export function operationalStatusClass(status: OperationalStatus | undefined | null): string {
  if (status === 'confirmed' || status === 'user-confirmed') return 'hub-status confirmed'
  if (status === 'reported' || status === 'estimated' || status === 'unverified' || status === 'info') return 'hub-status estimated'
  if (status === 'warning' || status === 'error' || status === 'critical') return 'hub-status conflict'
  if (status === 'stale') return 'hub-status stale'
  if (status === 'conflict') return 'hub-status conflict'
  if (status === 'unresolved') return 'hub-status unresolved'
  return 'hub-status unknown'
}
