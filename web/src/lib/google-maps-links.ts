export type MapsWaypointSource = 'coordinate' | 'text'
export type MapsTravelMode = 'driving' | 'walking' | 'transit' | 'bicycling'

export interface MapsStop {
  id?: string
  label: string
  mapsQuery?: string | null
  latitude?: number | null
  longitude?: number | null
}

export interface RouteDirectionChunk {
  id: string
  label: string
  href: string
  source: MapsStop
  destination: MapsStop
  waypoints: MapsStop[]
  sourceLabel: string
  destinationLabel: string
  fallbackReason?: string
}

const GOOGLE_MAPS_DIR_URL = 'https://www.google.com/maps/dir/?'
const GOOGLE_MAPS_SEARCH_URL = 'https://www.google.com/maps/search/?api=1&query='
// Five stops means origin + three waypoints + destination.
const MAX_WAYPOINTS_PER_ROUTE = 3
const MAX_MAPS_URL_LENGTH = 1900

function safeToString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  return ''
}

function safeToNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function mapsSource(stop: MapsStop): MapsWaypointSource {
  if (safeToNumber(stop.latitude) !== null && safeToNumber(stop.longitude) !== null) return 'coordinate'
  return 'text'
}

function stopQuery(stop: MapsStop): string {
  const lat = safeToNumber(stop.latitude)
  const lng = safeToNumber(stop.longitude)
  if (lat !== null && lng !== null) return `${lat},${lng}`
  return safeToString(stop.mapsQuery) || safeToString(stop.label) || 'unknown'
}

export function buildMapsSearchLink(placeLabel: string): string {
  return `${GOOGLE_MAPS_SEARCH_URL}${encodeURIComponent(safeToString(placeLabel) || 'point')}`
}

export function buildMapsDirectionsLink(chunks: MapsStop[], travelMode: MapsTravelMode = 'driving'): string {
  const start = chunks.at(0)
  const end = chunks.at(-1)
  if (!start || !end || chunks.length < 2) {
    return buildMapsSearchLink(chunks[0]?.label || '')
  }

  const waypoints = chunks.slice(1, -1)
  const params = new URLSearchParams({ api: '1', origin: stopQuery(start), destination: stopQuery(end), travelmode: travelMode })
  if (waypoints.length > 0) params.set('waypoints', waypoints.map(stopQuery).join('|'))
  const built = `${GOOGLE_MAPS_DIR_URL}${params.toString()}`
  return built.length <= MAX_MAPS_URL_LENGTH ? built : buildMapsSearchLink(`${stopQuery(start)} 到 ${stopQuery(end)}`)
}

function normalizeStops(stops: MapsStop[]): MapsStop[] {
  return stops
    .map((item, index) => ({
      ...item,
      id: item.id || `point-${index}`,
      label: safeToString(item.label) || `位置 ${index + 1}`,
    }))
    .filter((item) => item.label)
}

export function splitRouteStops(stops: MapsStop[], maxWaypoints = MAX_WAYPOINTS_PER_ROUTE): MapsStop[][] {
  const normalized = normalizeStops(stops)
  if (normalized.length <= 1) return []
  const maxPointsPerChunk = Math.max(2, maxWaypoints + 2)
  const chunks: MapsStop[][] = []
  let startIndex = 0

  while (startIndex < normalized.length - 1) {
    const endIndex = Math.min(startIndex + maxPointsPerChunk - 1, normalized.length - 1)
    chunks.push(normalized.slice(startIndex, endIndex + 1))
    if (endIndex === startIndex) {
      break
    }
    startIndex = endIndex
  }
  return chunks
}

export function buildRouteDirectionChunks(
  stops: MapsStop[],
  travelMode: MapsTravelMode = 'driving',
  maxWaypoints = MAX_WAYPOINTS_PER_ROUTE,
): RouteDirectionChunk[] {
  const chunks = splitRouteStops(stops, maxWaypoints)
  if (chunks.length === 0) return []

  return chunks.map((chunk, index) => {
    const source = chunk[0]
    const destination = chunk.at(-1) as MapsStop
    const waypoints = chunk.slice(1, -1)
    const href = buildMapsDirectionsLink(chunk, travelMode)
    const fallbackReason = undefined
    return {
      id: `${index + 1}`,
      label: `路線${String.fromCharCode(65 + index)}`,
      href,
      source,
      destination,
      waypoints,
      sourceLabel: source.label,
      destinationLabel: destination.label,
      fallbackReason,
    }
  })
}

export function enrichStopLabel(stop: MapsStop): string {
  const base = safeToString(stop.label)
  const coord = mapsSource(stop) === 'coordinate' ? `[${safeToNumber(stop.latitude)}, ${safeToNumber(stop.longitude)}]` : ''
  if (coord) {
    return `${base} ${coord}`
  }
  return base
}

export function formatStopRouteParts(stops: MapsStop[]): string {
  return normalizeStops(stops).map((item) => item.label).join(' → ')
}
