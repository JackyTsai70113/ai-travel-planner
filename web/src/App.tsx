import { useEffect, useMemo, useState } from 'react'
import {
  buildMapsSearchLink,
  buildRouteDirectionChunks,
  enrichStopLabel,
  type MapsStop,
  type RouteDirectionChunk,
} from './lib/google-maps-links'

interface BundleDayItem {
  id: string
  kind: string
  start_at: string | null
  end_at: string | null
  place_id: string
  notes?: string | null
}

interface BundlePlace {
  id: string
  name?: string | null
  address?: string | null
  kind?: string | null
  coordinates?: { lat: number; lng: number } | null
  maps_query?: string | null
  phone?: string | null
  mapcode?: string | null
  mapcode_jp?: string | null
  mapcode_tw?: string | null
  parking_availability?: string | null
  parking_fee?: string | null
  parking_height_limit?: string | null
  parking_large_vehicle_note?: string | null
  navigation_points?: unknown
  distance_from_parking_to_entrance?: string | null
  walking_distance_note?: string | null
  stroller_note?: string | null
}

interface BundleDay {
  date: string
  summary: string
  items: BundleDayItem[]
}

interface Constraint {
  id: string
  description: string
}

interface BundleTransportSummary {
  id: string
  from_label?: string | null
  to_label?: string | null
  from_place?: string | null
  to_place?: string | null
  mode: string
  status: string
  departure_at: string
  arrival_at: string
  estimated_duration_minutes?: number | null
  distance_km?: number | null
  note?: string | null
}

interface BundleTransportLeg {
  id?: string
  from_place_id?: string | null
  to_place_id?: string | null
  from?: string | null
  to?: string | null
  departure_at?: string | null
  arrival_at?: string | null
  mode?: string | null
  status?: string | null
  estimated_duration_minutes?: number | string | null
  distance_miles?: number | string | null
  distance_km?: number | string | null
  estimated_distance_meters?: number | string | null
  note?: string | null
  provenance?: { status?: string | null; note?: string | null; retrieved_at?: string | null } | null
}

interface BundleRouteWorkspace {
  date?: string
  status?: 'ok' | 'warning' | 'error' | 'unknown' | string
  source?: string | null
  retrieved_at?: string | null
  freshness?: 'fresh' | 'stale' | 'unverified' | 'conflicting' | string | null
  start_anchor_id?: string | null
  end_anchor_id?: string | null
  stops?: unknown
  segments?: unknown
  total_estimated_duration_minutes?: number | null
  total_estimated_distance_meters?: number | null
  segment_count?: number | null
  toll_road?: boolean | null
  has_etc?: boolean | null
  has_toll?: boolean | null
  no_route_reasons?: string[] | null
}

interface RouteSegmentDisplay {
  fromLabel: string
  toLabel: string
  mode: string
  durationText: string
  distanceText: string
  statusText: string
  sourceText: string
  freshnessText: string
  departureText: string
  arrivalText: string
  warningText: string[]
  canNavigate: boolean
}

interface StopNavigationTarget {
  id: string
  kind: string
  label: string
  mapsQuery?: string
  phone?: string
  mapcode?: string
  note?: string
}

interface DisplayStop {
  id: string
  label: string
  placeId?: string
  address?: string
  kind?: string
  note?: string
  mapsQuery?: string
  phone?: string
  mapcode?: string
  parking_availability?: string
  parking_fee?: string
  parking_height_limit?: string
  parking_large_vehicle_notes?: string
  distance_from_parking_to_entrance?: string
  stroller_note?: string
  entrance_type?: string
  source_state?: string
  navigationTargets: StopNavigationTarget[]
}

interface DailyRouteProjection {
  date: string
  status: 'ok' | 'warning' | 'error' | 'unknown'
  hasData: boolean
  routeSource: string
  routeFreshness: string
  startLabel: string
  endLabel: string
  totalDurationText: string
  totalDistanceText: string
  segmentCount: number
  tollRoad: boolean
  hasEtc: boolean
  warnings: string[]
  stops: DisplayStop[]
  segments: RouteSegmentDisplay[]
}

interface Bundle {
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
  transport_legs?: Array<BundleTransportLeg | BundleTransportSummary>
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

interface ChecklistState {
  [key: string]: boolean
}

interface DrivingOperationsRaw {
  raw_payload?: string | null
  rental_status?: string
  vehicle_recommendation?: string
  booking_state?: 'booked' | 'recommended' | 'unknown' | string
  child_seat_effective_seats?: number | string
  luggage_capacity_risk?: string
  elder_boarding_height?: string
  one_car_strategy?: string
  two_car_strategy?: string
  large_van_strategy?: string
  fuel_notes?: string | null
  nearest_verified_gas?: string[] | null
  return_car_checklist?: string[] | null
  return_strategy_8_30?: string | null
  return_strategy_8_31?: string | null
  day5_airport_backward_plan?: string | null
}

type AnyObj = Record<string, unknown>

const STORAGE_KEYS = {
  checklist: 'awaji_2026_checklist',
  notes: 'awaji_2026_notes',
  budget: 'awaji_2026_budget',
} as const

const DEFAULT_CHECKLIST: ChecklistState = {
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

const DEFAULT_TEXT = '--'
const UNKNOWN_TEXT = '待確認'

function safeParseJson<T>(value: string | null, fallback: T): T {
  if (!value) return fallback
  try {
    const parsed = JSON.parse(value)
    return parsed as T
  } catch {
    return fallback
  }
}

function asString(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed || undefined
  }
  return undefined
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value.trim())
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

function asBoolean(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value
  if (value === 'true') return true
  if (value === 'false') return false
  return undefined
}

function asCoordinate(value: unknown): { lat: number; lng: number } | undefined {
  const candidate = asRecord(value)
  if (!candidate) return undefined

  const lat = asNumber(candidate.lat) ?? asNumber(candidate.latitude)
  const lng = asNumber(candidate.lng) ?? asNumber(candidate.longitude)
  if (lat === undefined || lng === undefined) return undefined
  return { lat, lng }
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asRecord(value: unknown): AnyObj | undefined {
  if (value && typeof value === 'object') return value as AnyObj
  return undefined
}

function formatMoney(value: { amount: number; currency: string } | null): string {
  if (!value) return DEFAULT_TEXT
  return `${value.currency} ${value.amount.toLocaleString()}`
}

function toFriendlyStatus(status: Bundle['status']): string {
  if (status === 'ok') return '可執行'
  if (status === 'warning') return '待補資訊'
  return '嚴重訊息'
}

function mapStatusClass(status: Bundle['status']): string {
  if (status === 'ok') return 'status ok'
  if (status === 'warning') return 'status warning'
  return 'status error'
}

function toMinuteText(rawValue: number | null | undefined): string {
  if (rawValue === undefined || rawValue === null || rawValue <= 0) return UNKNOWN_TEXT
  return `${rawValue} 分鐘`
}

function toDistanceText(rawValue: number | null | undefined): string {
  if (rawValue === undefined || rawValue === null || rawValue <= 0) return UNKNOWN_TEXT
  if (rawValue >= 1000) return `${(rawValue / 1000).toFixed(1)} km`
  return `${rawValue} m`
}

function toPhoneTel(phone?: string): string {
  if (!phone) return ''
  return phone.replace(/[^+\d]/g, '')
}

function findPlaceById(places: BundlePlace[] = [], placeId: string): BundlePlace | undefined {
  return places.find((place) => place.id === placeId)
}

function parseNavigationPoint(raw: unknown): StopNavigationTarget | null {
  const point = asRecord(raw)
  if (!point) return null

  const id = asString(point.id) || `navigation-${Math.random().toString(36).slice(2, 9)}`
  const kind = asString(point.kind) || 'poi'
  const label = asString(point.name) || asString(point.label) || asString(point.title) || `${kind} 點位`
  const mapsQuery =
    asString(point.maps_query) ||
    asString(point.map_query) ||
    asString(point.query) ||
    asString(point.location) ||
    asString(point.mapsQuery)

  const coordinates = asCoordinate(point.coordinates)
  const finalQuery = mapsQuery || (coordinates ? `${coordinates.lat},${coordinates.lng}` : undefined)

  return {
    id,
    kind,
    label,
    mapsQuery: finalQuery,
    phone: asString(point.phone),
    mapcode: asString(point.mapcode) || asString(point.mapcode_jp) || asString(point.mapcode_tw),
    note: asString(point.note),
  }
}

function navigationTargetsFromStop(
  stop: AnyObj | undefined,
  place: BundlePlace | undefined,
  fallbackLabel: string,
): StopNavigationTarget[] {
  const result: StopNavigationTarget[] = []
  const seen = new Set<string>()

  const appendTarget = (target: StopNavigationTarget | null) => {
    if (!target || !target.label) return
    const map = target.mapsQuery || target.label
    const key = `${target.kind}::${map}`
    if (seen.has(key)) return
    if (!map.trim()) return
    seen.add(key)
    result.push(target)
  }

  asArray(stop?.navigation_points).forEach((entry) => appendTarget(parseNavigationPoint(entry)))
  asArray(place?.navigation_points).forEach((entry) => appendTarget(parseNavigationPoint(entry)))

  appendTarget({
    id: `main-${fallbackLabel}`,
    kind: 'poi',
    label: fallbackLabel,
    mapsQuery:
      asString(stop?.maps_query) ||
      asString(stop?.mapsQuery) ||
      asString(stop?.query) ||
      asString(place?.maps_query) ||
      asString(place?.name) ||
      asString(place?.address) ||
      fallbackLabel,
    note: asString(stop?.note),
  })

  return result
}

function navigationActionLabel(target: StopNavigationTarget): string {
  if (target.kind === 'parking') return '開啟停車場'
  if (target.kind === 'entrance') return '開啟入口'
  if (target.kind === 'meeting_point') return '開啟集合點'
  return '開啟 Google Maps'
}

function dayMatchTime(timeText: string | undefined, dayDate: string): boolean {
  if (!timeText) return false
  return timeText.startsWith(dayDate)
}

function segmentCanNavigate(statusText: string, noRoute: boolean, unknownRoute: boolean): boolean {
  if (noRoute || unknownRoute) return false
  const normalized = statusText.trim().toLowerCase()
  if (!normalized) return false
  if (normalized === 'ok' || normalized === 'estimated' || normalized === 'confirmed') return true
  if (normalized === 'warning' || normalized === 'error' || normalized === 'unresolved' || normalized === 'unknown' || normalized === 'missing') return false
  return true
}

function toPlaceLabel(places: BundlePlace[] = [], placeId: string): string {
  const found = findPlaceById(places, placeId)
  return found?.name || found?.maps_query || placeId
}

function buildDisplayStopFromItem(item: BundleDayItem, places: BundlePlace[], index: number): DisplayStop {
  const place = findPlaceById(places, item.place_id)
  const stopLabel = toPlaceLabel(places, item.place_id)
  const stopAsRecord: AnyObj | undefined = {
    maps_query: place?.maps_query,
    query: place?.maps_query,
    phone: place?.phone,
    mapcode: place?.mapcode,
    mapcode_jp: place?.mapcode_jp,
    mapcode_tw: place?.mapcode_tw,
    parking_availability: place?.parking_availability,
    parking_fee: place?.parking_fee,
    parking_height_limit: place?.parking_height_limit,
    parking_large_vehicle_note: place?.parking_large_vehicle_note,
    distance_from_parking_to_entrance: place?.distance_from_parking_to_entrance,
    stroller_note: place?.stroller_note,
    kind: place?.kind,
    point_type: stopLabel,
    name: place?.name || item.place_id,
  }
  const navigationTargets = navigationTargetsFromStop(stopAsRecord, place, stopLabel)

  return {
    id: item.id || `fallback-item-${index}`,
    label: stopLabel,
    placeId: item.place_id,
    address: place?.address,
    mapsQuery: navigationTargets[0]?.mapsQuery || place?.maps_query || place?.name,
    phone: place?.phone || undefined,
    mapcode: place?.mapcode || place?.mapcode_jp || place?.mapcode_tw || undefined,
    parking_availability: place?.parking_availability || undefined,
    parking_fee: place?.parking_fee || undefined,
    parking_height_limit: place?.parking_height_limit || undefined,
    parking_large_vehicle_notes: place?.parking_large_vehicle_note || undefined,
    distance_from_parking_to_entrance: place?.distance_from_parking_to_entrance || undefined,
    stroller_note: place?.stroller_note || undefined,
    kind: place?.kind || 'poi',
    note: item.notes || undefined,
    navigationTargets,
    source_state: 'from itinerary',
  }
}

function buildStopsFromRaw(rawStops: unknown, places: BundlePlace[]): DisplayStop[] {
  return asArray(rawStops).map((entry, index) => {
    const stop = asRecord(entry)
    if (!stop) {
      return {
        id: `raw-stop-${index}`,
        label: `站點 ${index + 1}`,
        kind: 'unknown',
      }
    }

    const placeId = asString(stop.place_id) || asString(stop.placeId)
    const label = asString(stop.label) || asString(stop.name) || asString(stop.title) || placeId || `站點 ${index + 1}`
    const place = placeId ? findPlaceById(places, placeId) : undefined
    const navigationTargets = navigationTargetsFromStop(stop, place, label)

    return {
      id: asString(stop.id) || asString(stop.identifier) || `stop-${index}`,
      label,
      placeId,
      address: asString(stop.address) || place?.address || undefined,
      mapsQuery: asString(stop.maps_query) || asString(stop.query) || place?.maps_query || place?.name || place?.address,
      phone: asString(stop.phone) || place?.phone || undefined,
      mapcode: asString(stop.mapcode) || asString(stop.mapcode_jp) || asString(stop.mapcode_tw) || place?.mapcode || place?.mapcode_jp || place?.mapcode_tw || undefined,
      parking_availability: asString(stop.parking_availability),
      parking_fee: asString(stop.parking_fee),
      parking_height_limit: asString(stop.parking_height_limit),
      parking_large_vehicle_notes: asString(stop.parking_large_vehicle_note),
      distance_from_parking_to_entrance: asString(stop.distance_from_parking_to_entrance),
      stroller_note: asString(stop.stroller_note),
      kind: asString(stop.kind) || place?.kind || 'unknown',
      entrance_type: asString(stop.point_type),
      note: asString(stop.note),
      navigationTargets,
      source_state: asString(stop.source_state) || asString(stop.state) || 'read-model',
    }
  })
}

function findRouteWorkspace(bundle: Bundle, date: string): BundleRouteWorkspace | undefined {
  const raw = bundle as AnyObj
  const candidates = [
    raw.daily_routes,
    raw.daily_route_workspaces,
    raw.route_workspaces,
    raw.route_workspace,
    raw.daily_route_workspace,
    raw.route_segments_by_day,
    raw.transport_workspace,
  ]

  for (const candidate of candidates) {
    const candidateObj = asRecord(candidate)
    if (candidateObj && asString(candidateObj.date) === date) {
      return candidateObj as BundleRouteWorkspace
    }

    const candidateArr = asArray(candidate)
    const hitFromList = candidateArr.find((entry) => asString(asRecord(entry)?.date) === date)
    if (hitFromList) return asRecord(hitFromList) as BundleRouteWorkspace

    const byDates = candidateObj ? asRecord(candidateObj[date]) : undefined
    if (byDates && asString(byDates.date) === date) {
      return byDates as BundleRouteWorkspace
    }
  }

  return undefined
}

function buildRouteSegments(rawSegments: unknown, fallbackStops: DisplayStop[]): RouteSegmentDisplay[] {
  const segments = asArray(rawSegments)
  if (segments.length > 0) {
    return segments.map((entry) => {
      const data = asRecord(entry) || {}
      const fromLabel = asString(data.from_label) || asString(data.from_place_id) || asString(data.from) || '未知起點'
      const toLabel = asString(data.to_label) || asString(data.to_place_id) || asString(data.to) || '未知終點'
      const duration = asNumber(data.estimated_duration_minutes)
      const rawDistanceMeters = asNumber(data.estimated_distance_meters)
      const distanceKm = asNumber(data.distance_km)
      const distance = rawDistanceMeters ?? (distanceKm === undefined ? undefined : distanceKm * 1000)
      const status = asString(data.status) || asString(data.provenance?.status) || 'unknown'
      const source = asString(data.source) || '未指定'
      const freshness = asString(data.source_state) || asString(data.freshness) || 'unverified'
      const unknownRoute = asString(data.unknown_route) === 'true' || asBoolean(data.unknown_route) === true
      const noRoute = Boolean(data.no_route) || Boolean(data.no_path) || unknownRoute
      const canNavigate = segmentCanNavigate(status, noRoute, unknownRoute)

      const warnings = [
        asString(data.parking),
        asString(data.unloading_note),
        asString(data.walking_note),
        asString(data.etc_risk),
        asString(data.rest_stop),
        asString(data.risk),
      ].filter((item): item is string => Boolean(item))

      return {
        fromLabel,
        toLabel,
        mode: asString(data.mode) || 'driving',
        durationText: canNavigate ? toMinuteText(duration) : UNKNOWN_TEXT,
        distanceText: canNavigate ? toDistanceText(distance) : UNKNOWN_TEXT,
        statusText: canNavigate ? status : '缺失路線',
        sourceText: source,
        freshnessText: freshness,
        departureText: formatTimeFromText(asString(data.departure_at) ?? null),
        arrivalText: formatTimeFromText(asString(data.arrival_at) ?? null),
        warningText: warnings,
        canNavigate,
      }
    })
  }

  if (fallbackStops.length <= 1) return []
  return fallbackStops.slice(0, -1).map((from, index) => {
    const to = fallbackStops[index + 1]
    return {
      fromLabel: from.label,
      toLabel: to.label,
      mode: 'driving',
      durationText: UNKNOWN_TEXT,
      distanceText: UNKNOWN_TEXT,
      statusText: UNKNOWN_TEXT,
      sourceText: 'from itinerary',
      freshnessText: 'unverified',
      departureText: '—',
      arrivalText: '—',
      warningText: ['無法從 read-model 取得段落估時，請出發前再次確認。'],
      canNavigate: false,
    }
  })
}

function buildTransportLegsProjection(bundle: Bundle, dayDate: string): {
  routeStops: DisplayStop[]
  segments: RouteSegmentDisplay[]
  totalDuration: number | undefined
  totalDistance: number | undefined
  status: DailyRouteProjection['status']
  warnings: string[]
  hasData: boolean
} {
  const rawLegs = asArray((bundle as AnyObj).transport_legs)
  const legRows = rawLegs
    .map((entry) => asRecord(entry) || {})
    .filter((leg) => {
      const departure = asString(leg.departure_at) || asString(leg.start_time) || asString(leg.start_at)
      const arrival = asString(leg.arrival_at) || asString(leg.end_time) || asString(leg.end_at)
      return dayMatchTime(departure, dayDate) || dayMatchTime(arrival, dayDate)
    })

  if (legRows.length === 0) {
    return { routeStops: [], segments: [], totalDuration: undefined, totalDistance: undefined, status: 'unknown', warnings: [], hasData: false }
  }

  const routeStops: DisplayStop[] = []
  const segments: RouteSegmentDisplay[] = []
  let totalDuration = 0
  let totalDistance = 0
  let hasUnknownSegment = false
  const warnings: string[] = []

  legRows.forEach((leg, index) => {
    const fromPlaceId = asString(leg.from_place_id) || asString(leg.from)
    const toPlaceId = asString(leg.to_place_id) || asString(leg.to)
    const fromLabel = toPlaceLabel(bundle.places || [], fromPlaceId || `起點 ${index + 1}`)
    const toLabel = toPlaceLabel(bundle.places || [], toPlaceId || `終點 ${index + 1}`)

    const fromStop = fromPlaceId
      ? buildDisplayStopFromItem(
          {
            id: `transport-leg-${index}-from`,
            kind: 'transport',
            place_id: fromPlaceId,
            start_at: null,
            end_at: null,
          },
          bundle.places || [],
          routeStops.length + 1,
        )
      : null
    const toStop = toPlaceId
      ? buildDisplayStopFromItem(
          {
            id: `transport-leg-${index}-to`,
            kind: 'transport',
            place_id: toPlaceId,
            start_at: null,
            end_at: null,
          },
          bundle.places || [],
          routeStops.length + 2,
        )
      : null

    if (!routeStops.length && fromStop) routeStops.push(fromStop)
    if (toStop && routeStops.at(-1)?.placeId !== toStop.placeId) routeStops.push(toStop)

    const duration = asNumber(leg.estimated_duration_minutes)
    const distanceKm = asNumber(leg.distance_km)
    const distanceMeters = asNumber(leg.estimated_distance_meters) ?? (distanceKm === undefined ? undefined : distanceKm * 1000)
    const status = asString(leg.status) || asString(leg.provenance?.status) || 'estimated'
    const isUnknown = asBoolean(leg.unknown) || asBoolean(leg.unknown_route) || asString(leg.status) === 'unknown'
    const canNavigate = segmentCanNavigate(status, asBoolean(leg.no_route) === true, isUnknown)
    const warningsForSegment = [asString(leg.note), asString(leg.risk), asString(leg.provenance?.note)].filter(
      (item): item is string => Boolean(item),
    )

    if (!canNavigate) warnings.push(`leg-${index + 1}：${status}`)
    if (warningsForSegment.length > 0) {
      warnings.push(...warningsForSegment)
    }

    if (duration) totalDuration += duration
    if (distanceMeters) totalDistance += distanceMeters
    if (!canNavigate) hasUnknownSegment = true

    segments.push({
      fromLabel: fromLabel,
      toLabel,
      mode: asString(leg.mode) || 'driving',
      durationText: canNavigate && duration ? `${duration} 分鐘` : UNKNOWN_TEXT,
      distanceText: canNavigate && distanceMeters ? (distanceMeters >= 1000 ? `${(distanceMeters / 1000).toFixed(1)} km` : `${distanceMeters} m`) : UNKNOWN_TEXT,
      statusText: canNavigate ? status : '缺失路線',
      sourceText: asString(leg.source) || asString(leg.status_source) || 'transport_legs',
      freshnessText: asString(leg.freshness) || asString(leg.state) || 'unverified',
      departureText: formatTimeFromText(asString(leg.departure_at)),
      arrivalText: formatTimeFromText(asString(leg.arrival_at)),
      warningText: warningsForSegment,
      canNavigate,
    })
  })

  return {
    routeStops,
    segments,
    totalDuration: totalDuration || undefined,
    totalDistance: totalDistance || undefined,
    status: hasUnknownSegment ? 'warning' : 'ok',
    warnings,
    hasData: true,
  }
}

function buildDailyRoute(bundle: Bundle | null, day: BundleDay | null): DailyRouteProjection | null {
  if (!bundle || !day) return null
  const routeWorkspace = findRouteWorkspace(bundle, day.date)

  const routeStops = buildStopsFromRaw(routeWorkspace?.stops, bundle.places || [])
  const fallbackStops = day.items.map((item, index) => buildDisplayStopFromItem(item, bundle.places || [], index))
  const transportFallback = buildTransportLegsProjection(bundle, day.date)
  const hasRouteWorkspace = routeStops.length > 0 || asArray(routeWorkspace?.segments).length > 0

  const stops = routeStops.length > 0 ? routeStops : transportFallback.routeStops.length > 0 ? transportFallback.routeStops : fallbackStops
  const segments = hasRouteWorkspace
    ? buildRouteSegments(routeWorkspace?.segments, stops)
    : transportFallback.routeStops.length > 0
      ? transportFallback.segments
      : buildRouteSegments(undefined, stops)

  const status = hasRouteWorkspace
    ? ((asString(routeWorkspace?.status) as DailyRouteProjection['status']) || 'warning')
    : segments.some((segment) => !segment.canNavigate)
      ? 'warning'
      : (transportFallback.status || 'warning')
  const totalDuration = hasRouteWorkspace
    ? asNumber(routeWorkspace?.total_estimated_duration_minutes)
    : transportFallback.totalDuration
  const totalDistance = hasRouteWorkspace
    ? asNumber(routeWorkspace?.total_estimated_distance_meters)
    : transportFallback.totalDistance

  const warnings: string[] = []
  if (asBoolean(routeWorkspace?.has_toll)) warnings.push('含收費道路，可能涉及通行費')
  if (asBoolean(routeWorkspace?.has_etc)) warnings.push('該路線有 ETC 訊息')
  if (transportFallback.warnings.length > 0) warnings.push(...transportFallback.warnings)
  if (segments.some((segment) => segment.statusText === '缺失路線')) {
    warnings.push('有路段缺失路線，請臨場轉線')
  }

  return {
    date: day.date,
    status: status || 'warning',
    hasData: routeStops.length > 0 || asArray(routeWorkspace?.segments).length > 0 || transportFallback.hasData,
    routeSource: asString(routeWorkspace?.source) || (transportFallback.hasData ? 'transport_legs' : 'itinerary fallback'),
    routeFreshness: asString(routeWorkspace?.freshness) || (transportFallback.hasData ? 'stale' : 'unknown'),
    startLabel: stops[0]?.label || DEFAULT_TEXT,
    endLabel: stops.at(-1)?.label || DEFAULT_TEXT,
    totalDurationText: hasDurationTotal(totalDuration, routeWorkspace?.status),
    totalDistanceText: hasDistanceTotal(totalDistance, routeWorkspace?.status),
    segmentCount: segments.length,
    tollRoad: asBoolean(routeWorkspace?.toll_road) || false,
    hasEtc: asBoolean(routeWorkspace?.has_etc) || false,
    warnings,
    stops,
    segments,
  }
}

function hasDurationTotal(value: number | undefined, status?: string): string {
  if (!value || value <= 0) {
    if (status === 'ok') return '0'
    return UNKNOWN_TEXT
  }
  return `${value} 分鐘`
}

function hasDistanceTotal(value: number | undefined, status?: string): string {
  if (!value || value <= 0) {
    if (status === 'ok') return '0'
    return UNKNOWN_TEXT
  }
  return value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${value} m`
}

function toMapsStops(stops: DisplayStop[]): MapsStop[] {
  const pickPrimary = (stop: DisplayStop): string | undefined => {
    const primary = stop.navigationTargets?.find((target) => target.kind === 'poi') || stop.navigationTargets?.[0]
    return primary?.mapsQuery || stop.mapsQuery
  }
  return stops.map((stop) => ({
    id: stop.id,
    label: enrichStopLabel({ id: stop.id, label: stop.label, mapsQuery: pickPrimary(stop) }),
    mapsQuery: pickPrimary(stop),
  }))
}

function mapFreshnessBadge(freshness: string): string {
  if (freshness === 'fresh') return 'status ok'
  if (freshness === 'stale') return 'status warning'
  if (freshness === 'conflicting') return 'status error'
  return 'status warning'
}

function toRouteStatusClass(status: DailyRouteProjection['status']): string {
  if (status === 'ok') return 'status ok'
  if (status === 'warning') return 'status warning'
  return status === 'error' ? 'status error' : 'status warning'
}

function formatTimeFromText(timeText: string | null): string {
  if (!timeText) return '—'
  const parsed = new Date(timeText)
  if (Number.isNaN(parsed.getTime())) return timeText
  return parsed.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

function parseDrivingOperations(bundle: Bundle | null): DrivingOperationsRaw | null {
  if (!bundle) return null
  const raw = asRecord((bundle as AnyObj).driving_operations) || asRecord((bundle as AnyObj).operations)
  if (!raw) return null

  if ((bundle as AnyObj).operations && !(bundle as AnyObj).driving_operations) {
    return { raw_payload: JSON.stringify(raw, null, 2) }
  }

  return {
    rental_status: asString(raw.rental_status),
    vehicle_recommendation: asString(raw.vehicle_recommendation),
    booking_state: asString(raw.booking_state),
    child_seat_effective_seats: asNumber(raw.child_seat_effective_seats),
    luggage_capacity_risk: asString(raw.luggage_capacity_risk),
    elder_boarding_height: asString(raw.elder_boarding_height),
    one_car_strategy: asString(raw.one_car_strategy),
    two_car_strategy: asString(raw.two_car_strategy),
    large_van_strategy: asString(raw.large_van_strategy),
    fuel_notes: asString(raw.fuel_notes),
    nearest_verified_gas: asArray(raw.nearest_verified_gas).map((item) => asString(item)).filter((item): item is string => !!item),
    return_car_checklist: asArray(raw.return_car_checklist).map((item) => asString(item)).filter((item): item is string => !!item),
    return_strategy_8_30: asString(raw.return_strategy_8_30),
    return_strategy_8_31: asString(raw.return_strategy_8_31),
    day5_airport_backward_plan: asString(raw.day5_airport_backward_plan),
  }
}

function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [error, setError] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [activeDay, setActiveDay] = useState(0)
  const [copiedId, setCopiedId] = useState<string>('')
  const [isOnline, setIsOnline] = useState(true)
  const [checklist, setChecklist] = useState<ChecklistState>(DEFAULT_CHECKLIST)
  const [notes, setNotes] = useState<string>('')
  const [tripBudgetMemo, setTripBudgetMemo] = useState<string>('')
  const [nextStopByDay, setNextStopByDay] = useState<Record<string, number>>({})

  useEffect(() => {
    setChecklist(safeParseJson(localStorage.getItem(STORAGE_KEYS.checklist), DEFAULT_CHECKLIST))
    setNotes(safeParseJson(localStorage.getItem(STORAGE_KEYS.notes), ''))
    setTripBudgetMemo(safeParseJson(localStorage.getItem(STORAGE_KEYS.budget), ''))
    setIsOnline(window.navigator.onLine)

    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.checklist, JSON.stringify(checklist))
  }, [checklist])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.notes, JSON.stringify(notes))
  }, [notes])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.budget, JSON.stringify(tripBudgetMemo))
  }, [tripBudgetMemo])

  useEffect(() => {
    const load = async () => {
      const baseUrl = String(import.meta.env.BASE_URL || '/')
      setLoading(true)
      setError('')

      try {
        const urls = [
          `${baseUrl}public-bundle.json`,
          `${baseUrl}trips/awaji-2026/public-bundle.json`,
          './public-bundle.json',
          './trips/awaji-2026/public-bundle.json',
        ]
        const attemptLogs: string[] = []
        let response: Response | null = null

        for (const candidate of urls) {
          try {
            const result = await fetch(candidate)
            if (result.ok) {
              response = result
              break
            }
            attemptLogs.push(`${candidate} => HTTP ${result.status}`)
          } catch {
            attemptLogs.push(`${candidate} => network error`)
          }
        }

        if (!response) {
          throw new Error(`public-bundle.json 無法載入（已嘗試 ${urls.join('、')}；${attemptLogs.join('；')}）`)
        }
        const data = (await response.json()) as Bundle
        setBundle(data)
        setActiveDay(Math.min(0, Math.max(data.days.length - 1, 0)))
      } catch (err) {
        setError(err instanceof Error ? err.message : '載入發生未知錯誤')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [])

  const totalDays = useMemo(() => bundle?.days.length ?? 0, [bundle])
  const placeList = useMemo(() => bundle?.places ?? [], [bundle])
  const warningCount = useMemo(
    () => bundle?.validation.filter((item) => item.severity === 'warning' || item.severity === 'error').length ?? 0,
    [bundle],
  )
  const unresolvedReservations = useMemo(
    () => bundle?.reservations.filter((reservation) => reservation.unresolved) ?? [],
    [bundle],
  )

  const currentDay = bundle?.days[activeDay] ?? null
  const dayRoute = useMemo(() => buildDailyRoute(bundle, currentDay), [bundle, currentDay])

  const routeChunks = useMemo<RouteDirectionChunk[]>(() => {
    if (!dayRoute || dayRoute.stops.length < 2) return []
    const mapsStops = toMapsStops(dayRoute.stops)
    return buildRouteDirectionChunks(mapsStops, 8)
  }, [dayRoute])

  const routeChunksNavigable = Boolean(
    dayRoute && dayRoute.stops.length >= 2 && dayRoute.segments.length > 0 && dayRoute.segments.every((segment) => segment.canNavigate),
  )

  const drivingOps = useMemo(() => parseDrivingOperations(bundle), [bundle])

  const checklistProgress = useMemo(() => {
    const total = Object.keys(DEFAULT_CHECKLIST).length
    const done = Object.entries(checklist).filter((entry) => entry[1]).length
    return { total, done, rate: total === 0 ? 0 : Math.round((done / total) * 100) }
  }, [checklist])

  const copyText = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(label)
      setTimeout(() => setCopiedId((current) => (current === label ? '' : current)), 1200)
    } catch {
      setError('複製失敗：你的瀏覽器未允許剪貼簿操作')
    }
  }

  const nextStopIndex = currentDay ? Math.min(nextStopByDay[currentDay.date] || 0, Math.max(0, (dayRoute?.stops.length ?? 1) - 2)) : 0

  const goToNextStop = () => {
    if (!isOnline) {
      setError('目前離線，無法直接開啟 Google Maps 導航。可先複製地址後改用現場行動。')
      return
    }

    if (!dayRoute || dayRoute.stops.length < 2 || !currentDay) {
      setError('本日目前沒有可導航的停靠點。')
      return
    }

    const fromStop = dayRoute.stops[nextStopIndex]
    const toStop = dayRoute.stops[nextStopIndex + 1]
    const selectedSegment = dayRoute.segments[nextStopIndex]
    if (selectedSegment && !selectedSegment.canNavigate) {
      setError('目前路段無法導航。請先檢查路線摘要中的「缺失路線」提示。')
      return
    }

    const directChunks = buildRouteDirectionChunks(toMapsStops([fromStop, toStop]), 1)
    const finalLink = directChunks[0]?.href ?? buildMapsSearchLink(`${fromStop.label} -> ${toStop.label}`)

    window.open(finalLink, '_blank', 'noopener')
    setNextStopByDay((current) => ({
      ...current,
      [currentDay.date]: Math.min(nextStopIndex + 1, dayRoute.stops.length - 2),
    }))
  }

  const printRouteSummary = () => {
    window.print()
  }

  if (loading) {
    return <main className="shell">讀取行程中…</main>
  }

  if (error || !bundle) {
    return <main className="shell">{error || '資料異常'}</main>
  }

  return (
    <main className="shell">
      <header className="hero">
        <p className="eyebrow">2026 淡路島・鳴門家庭旅行</p>
        <h1>{bundle.title}</h1>
        <div className="hero-meta">
          <span>{bundle.date_range.start_date} ~ {bundle.date_range.end_date}</span>
          <span className={mapStatusClass(bundle.status)}>行程狀態：{toFriendlyStatus(bundle.status)}</span>
        </div>
        <p className={isOnline ? 'online' : 'offline'}>
          {isOnline ? '線上模式：可直接開啟 Google Maps 與通訊動作' : '離線模式：保留行程欄位與備忘，外部連結會提示'}
        </p>
      </header>

      <section className="card">
        <h2>旅程總覽</h2>
        <div className="grid two-col">
          <p>時區：{bundle.local_timezone}</p>
          <p>總天數：{totalDays} 天</p>
          <p>大人：{bundle.traveler_profile.adults}</p>
          <p>小孩：{bundle.traveler_profile.children_count}</p>
          <p>小孩年齡：{bundle.traveler_profile.children_ages.join(', ') || '未提供'}</p>
          <p>待補提醒：{warningCount} 筆</p>
          <p>資料更新：{bundle.meta.generated_at}</p>
        </div>
        <div className="toolbar">
          <button type="button" onClick={printRouteSummary}>列印旅程摘要</button>
          <button
            type="button"
            onClick={() =>
              copyText('summary', `出發日程：${bundle.title}（${bundle.date_range.start_date}~${bundle.date_range.end_date}）`)
            }
          >
            {copiedId === 'summary' ? '已複製' : '複製行程摘要'}
          </button>
        </div>
      </section>

      <section className="card">
        <h2>每日路線工作台</h2>
        <div className="day-tabs" role="tablist" aria-label="行程日程頁籤">
          {bundle.days.map((day, index) => (
            <button
              key={day.date}
              className={`day-tab ${index === activeDay ? 'active' : ''}`}
              role="tab"
              aria-selected={index === activeDay}
              onClick={() => setActiveDay(index)}
              type="button"
            >
              Day {index + 1}
              <span>{day.date}</span>
            </button>
          ))}
        </div>

        {currentDay ? (
          <>
            {dayRoute ? (
              <article className="day">
                <div className="route-topline">
                  <h3>{currentDay.date}</h3>
                  <p className={toRouteStatusClass(dayRoute.status)}>
                    路線狀態：{dayRoute.status === 'ok' ? '可行' : dayRoute.status === 'warning' ? '待補' : '不可用'}
                  </p>
                </div>
                <p>{currentDay.summary}</p>
                <p className="muted">起點：{dayRoute.startLabel} / 終點：{dayRoute.endLabel}</p>
                <div className="grid three-col">
                  <p>總估時：{dayRoute.totalDurationText}</p>
                  <p>總距離：{dayRoute.totalDistanceText}</p>
                  <p>段數：{dayRoute.segmentCount}</p>
                </div>
                <p className={`muted ${mapFreshnessBadge(dayRoute.routeFreshness)}`}>
                  來源：{dayRoute.routeSource}，freshness：{dayRoute.routeFreshness}
                </p>

                {dayRoute.warnings.length ? (
                  <ul className="warning-list">
                    {dayRoute.warnings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}

                <h4>路線段</h4>
                <div className="route-segments">
                  {dayRoute.segments.length ? (
                    dayRoute.segments.map((segment, index) => (
                      <section className="segment-card" key={`${segment.fromLabel}-${segment.toLabel}-${index}`}>
                        <div className="segment-card__meta">
                          <strong>{segment.fromLabel} → {segment.toLabel}</strong>
                          <span className="segment-mode">{segment.mode}</span>
                        </div>
                        {segment.departureText !== '—' ? <p>出發時間：{segment.departureText}</p> : null}
                        {segment.arrivalText !== '—' ? <p>抵達時間：{segment.arrivalText}</p> : null}
                        <p>時長：{segment.durationText} / 距離：{segment.distanceText}</p>
                        <p>來源：{segment.sourceText}</p>
                        <p>freshness：{segment.freshnessText}</p>
                        <p>風險：{segment.statusText}{segment.canNavigate ? '' : '（不可直接導航）'}</p>
                        {segment.warningText.length ? <ul>{segment.warningText.map((item) => <li key={item}>{item}</li>)}</ul> : null}
                      </section>
                    ))
                  ) : <p>本日未提供段落資料。</p>}
                </div>

                <h4>每日停靠順序</h4>
                <ol className="stop-list">
                  {dayRoute.stops.map((stop, index) => (
                    <li key={stop.id}>
                      <div className="stop-index">{index + 1}</div>
                      <div className="stop-details">
                        <strong>{stop.label}</strong>
                        {stop.note ? <span>{stop.note}</span> : null}
                        {stop.address ? <span>地址：{stop.address}</span> : null}
                        {stop.phone ? <a href={`tel:${toPhoneTel(stop.phone)}`}>撥打電話：{stop.phone}</a> : null}
                        {stop.mapcode ? <span>Mapcode：{stop.mapcode}</span> : null}
                        {stop.entrance_type ? <span>入口類型：{stop.entrance_type}</span> : null}
                        {stop.parking_availability ? <span>停車：{stop.parking_availability}</span> : null}
                        {stop.parking_fee ? <span>停車費：{stop.parking_fee}</span> : null}
                        {stop.parking_height_limit ? <span>高度限制：{stop.parking_height_limit}</span> : null}
                        {stop.parking_large_vehicle_notes ? <span>大型車：{stop.parking_large_vehicle_notes}</span> : null}
                        {stop.distance_from_parking_to_entrance ? <span>步行：{stop.distance_from_parking_to_entrance}</span> : null}
                        {stop.stroller_note ? <span>推嬰兒車：{stop.stroller_note}</span> : null}
                        <div className="inline-actions">
                          {isOnline ? (
                            stop.navigationTargets.map((target) => (
                              <a
                                key={`${stop.id}-${target.id}`}
                                href={buildMapsSearchLink(target.mapsQuery || target.label)}
                                target="_blank"
                                rel="noreferrer"
                                title={navigationActionLabel(target)}
                              >
                                {navigationActionLabel(target)}
                              </a>
                            ))
                          ) : (
                            <span className="offline-note">離線：外部地圖無法開啟</span>
                          )}
                          <button type="button" onClick={() => copyText(`${currentDay.date}-${stop.id}-name`, stop.label)}>
                            {copiedId === `${currentDay.date}-${stop.id}-name` ? '已複製名稱' : '複製名稱'}
                          </button>
                          <button type="button" onClick={() => copyText(`${currentDay.date}-${stop.id}`, stop.mapsQuery || stop.address || stop.label)}>
                            {copiedId === `${currentDay.date}-${stop.id}` ? '已複製' : '複製地址'}
                          </button>
                          {stop.mapcode ? (
                            <button type="button" onClick={() => copyText(`${currentDay.date}-${stop.id}-mapcode`, stop.mapcode || '')}>
                              {copiedId === `${currentDay.date}-${stop.id}-mapcode` ? '已複製' : '複製 Mapcode'}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>

                {routeChunks.length ? (
                  <>
                    <h4>Google Maps 路線（可分段）</h4>
                    <div className="route-links">
                      {routeChunks.map((chunk) => (
                        <div key={`${chunk.id}-${chunk.label}`} className="route-link-row">
                          {isOnline && routeChunksNavigable ? (
                            <a
                              href={chunk.href}
                              target="_blank"
                              rel="noreferrer"
                              aria-label={`${chunk.label}：${chunk.source.label} 到 ${chunk.destination.label}`}
                            >
                              {chunk.label}（{chunk.sourceLabel} → {chunk.destinationLabel}）
                              {chunk.fallbackReason ? <span className="muted">，已回退為關鍵字搜尋</span> : null}
                            </a>
                          ) : isOnline ? (
                            <span className="offline-note">目前有不可導航路段，請先以停靠順序與段落摘要確認後再規劃。</span>
                          ) : (
                            <span className="offline-note">離線：{chunk.label} 需要網路開啟</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </>
                ) : null}
              </article>
            ) : null}
          </>
        ) : null}
      </section>

      <section className="card">
        <h2>固定預約</h2>
        {bundle.reservations.length ? (
          <ul>
            {bundle.reservations.map((reservation) => (
              <li key={reservation.id}>
                <span>
                  {reservation.day} · {formatTimeFromText(reservation.time)} · {reservation.name || '固定預約（待補）'} ({reservation.kind})
                </span>
                <span>地點：{toPlaceLabel(placeList, reservation.place_id)}</span>
                <button
                  type="button"
                  onClick={() => copyText(reservation.id, `${reservation.day} ${reservation.time ?? ''} ${reservation.name ?? ''}`.trim())}
                >
                  {copiedId === reservation.id ? '已複製' : '複製預約'}
                </button>
                {reservation.unresolved ? '（地點與持續時間待補）' : ''}
                <a href={buildMapsSearchLink(toPlaceLabel(placeList, reservation.place_id))} target="_blank" rel="noreferrer">
                  到預約地點
                </a>
              </li>
            ))}
          </ul>
        ) : <p>目前無固定預約。</p>}
        {unresolvedReservations.length > 0 ? <p>固定預約仍有待補：{unresolvedReservations.length} 筆。</p> : null}
      </section>

      <section className="card">
        <h2>駕駛作業中心</h2>
        {drivingOps ? (
          <div className="driver-card">
            {drivingOps.raw_payload ? (
              <>
                <h4>作業原始資料</h4>
                <pre className="snapshot-text">{drivingOps.raw_payload}</pre>
              </>
            ) : (
              <>
                <p>租車狀態：{drivingOps.rental_status || '未提供'}</p>
                <p>車型建議：{drivingOps.vehicle_recommendation || '未提供'}</p>
                <p>狀態標記：{drivingOps.booking_state || 'unknown'}</p>
                <p>安全座椅有效席位：{drivingOps.child_seat_effective_seats || '未提供'}</p>
                <p>行李容積風險：{drivingOps.luggage_capacity_risk || '未提供'}</p>
                <p>長輩上下車高度需求：{drivingOps.elder_boarding_height || '未提供'}</p>
                <h4>加油與還車策略</h4>
                <p>Fuel：{drivingOps.fuel_notes || '未提供'}</p>
                <p>8/30 還車：{drivingOps.return_strategy_8_30 || '未提供'}</p>
                <p>8/31 還車：{drivingOps.return_strategy_8_31 || '未提供'}</p>
                <p>Day 5 機場返程：{drivingOps.day5_airport_backward_plan || '未提供'}</p>
                {drivingOps.nearest_verified_gas?.length ? (
                  <>
                    <h4>最近加油站</h4>
                    <ul>{drivingOps.nearest_verified_gas.map((item) => <li key={item}>{item}</li>)}</ul>
                  </>
                ) : null}
                {drivingOps.return_car_checklist?.length ? (
                  <>
                    <h4>還車檢查</h4>
                    <ul>{drivingOps.return_car_checklist.map((item) => <li key={item}>{item}</li>)}</ul>
                  </>
                ) : null}
              </>
            )}
          </div>
        ) : <p>目前未提供駕駛作業資料。</p>}
      </section>

      <section className="card">
        <h2>行李與備忘（本機保存）</h2>
        <div className="muted">完成率：{checklistProgress.done}/{checklistProgress.total}（{checklistProgress.rate}%）</div>
        <ul className="checklist">
          {Object.entries(checklist).map(([key, checked]) => (
            <li key={key}>
              <label>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))}
                />
                {key === 'passport'
                  ? '護照/身分文件'
                  : key === 'twn_license'
                  ? '台灣駕照與國際駕照文件'
                  : key === 'insurance'
                  ? '汽車險與 rental 文件'
                  : key === 'itinerary_print'
                  ? '行程頁列印檔'
                  : key === 'cash_change'
                  ? '零用金與零錢'
                  : key === 'child_supplies'
                  ? '嬰幼兒用品/奶瓶'
                  : key === 'elder_med'
                  ? '長輩基本藥物與緊急連絡'
                  : key === 'heat_rain'
                  ? '防曬與防暑／雨具'
                  : key === 'car_docs'
                  ? '汽車文件與接送人聯絡方式'
                  : '急救用品'}
              </label>
            </li>
          ))}
        </ul>
        <label className="budget-note" htmlFor="tripNotes">臨時備註</label>
        <textarea
          id="tripNotes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="例如：8/28 前往鳴門前是否遇到塞車，或替代店家安排"
        />
        <label className="budget-note" htmlFor="budgetMemo">預算補充（僅本機）</label>
        <textarea
          id="budgetMemo"
          value={tripBudgetMemo}
          onChange={(event) => setTripBudgetMemo(event.target.value)}
          placeholder="例如：某日臨時超商、收費路線停車補貼"
        />
      </section>

      <section className="card">
        <h2>預算與提醒</h2>
        <p>總預算：{formatMoney(bundle.budget.total)}</p>
        <dl>
          {Object.entries(bundle.budget.categories).map(([category, amount]) => (
            <div className="budget-row" key={category}>
              <dt>{category}</dt>
              <dd>{formatMoney(amount)}</dd>
            </div>
          ))}
        </dl>
        <h3>硬限制</h3>
        <ul>{bundle.preferences.hard_constraints.map((item) => <li key={item.id}>{item.description}</li>)}</ul>
        <h3>提醒（{warningCount}）</h3>
        {bundle.validation.length ? <ul>{bundle.validation.map((item) => <li key={item.code}>{item.message}</li>)}</ul> : <p>目前無未確定提醒。</p>}
      </section>

      <section className="card bottom-action-bar">
        <button type="button" className="primary" onClick={goToNextStop}>
          一鍵導航下一站
        </button>
        <p className="muted">
          目前下一站：{currentDay ? `${nextStopIndex + 1} / ${dayRoute?.stops.length || 0}` : '未指定'}
        </p>
      </section>
    </main>
  )
}

export default App
