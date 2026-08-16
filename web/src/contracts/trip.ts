export interface BundleDayItem {
  id: string
  kind: string
  start_at: string | null
  end_at: string | null
  place_id: string
  notes?: string
}

export interface BundlePlace {
  id: string
  name?: string | null
  address?: string | null
  kind?: string | null
  maps_query?: string | null
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
  days: BundleDay[]
  reservations: {
    id: string
    day: string
    time: string | null
    name: string | null
    place_id: string
    kind: string
    unresolved?: boolean
  }[]
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
