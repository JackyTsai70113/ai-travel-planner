import { useEffect, useMemo, useState } from 'react'
import { TripRoute } from '../app/route-registry'
import {
  Bundle,
  BundleDay,
  BundleTransportLeg,
  operationalStatusClass,
  operationalStatusLabel,
} from '../contracts/trip'
import {
  MapsStop,
  MapsTravelMode,
  RouteDirectionChunk,
  buildMapsDirectionsLink,
  buildRouteDirectionChunks,
} from '../lib/google-maps-links'

interface MapPageProps {
  bundle: Bundle
  route: TripRoute
  currentDay?: string
}

function formatDay(date: string): string {
  try {
    return new Intl.DateTimeFormat('zh-TW', {
      month: 'numeric',
      day: 'numeric',
      weekday: 'short',
      timeZone: 'Asia/Tokyo',
    }).format(new Date(`${date}T00:00:00+09:00`))
  } catch {
    return date
  }
}

function formatTime(value: string | null): string {
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '—'
}

function transportModeLabel(mode: string): string {
  const labels: Record<string, string> = {
    car: '自駕',
    drive: '自駕',
    driving: '自駕',
    walk: '步行',
    walking: '步行',
    ferry: '渡輪',
    train: '鐵路',
    bus: '巴士',
    flight: '航班',
  }
  return labels[mode.toLowerCase()] || mode || '交通'
}

export function legTravelMode(mode: string): MapsTravelMode {
  if (mode === 'walk' || mode === 'walking') return 'walking'
  if (mode === 'bus' || mode === 'train' || mode === 'transit' || mode === 'ferry') return 'transit'
  if (mode === 'bicycle' || mode === 'bicycling') return 'bicycling'
  return 'driving'
}

function dayLegs(bundle: Bundle, day: BundleDay): BundleTransportLeg[] {
  const linkedIds = new Set(day.items.map((item) => item.transport_leg_id).filter(Boolean))
  const seen = new Set<string>()
  return (bundle.transport_legs || [])
    .filter((leg) => linkedIds.has(leg.id) || leg.departure_at?.slice(0, 10) === day.date)
    .filter((leg) => {
      if (seen.has(leg.id)) return false
      seen.add(leg.id)
      return true
    })
    .sort((a, b) => (a.departure_at || '').localeCompare(b.departure_at || ''))
}

function stopFor(bundle: Bundle, placeId: string, fallbackLabel: string): MapsStop {
  const place = bundle.places?.find((candidate) => candidate.id === placeId)
  return {
    id: placeId,
    label: place?.name || fallbackLabel || placeId,
    mapsQuery: place?.maps_query || place?.address || fallbackLabel || placeId,
  }
}

function routeStops(bundle: Bundle, legs: BundleTransportLeg[]): MapsStop[] {
  const stops: MapsStop[] = []
  legs.forEach((leg) => {
    const from = stopFor(bundle, leg.from_place, leg.from_label)
    const to = stopFor(bundle, leg.to_place, leg.to_label)
    if (stops.at(-1)?.id !== from.id) stops.push(from)
    if (stops.at(-1)?.id !== to.id) stops.push(to)
  })
  return stops
}

export interface ContiguousLegGroup {
  id: string
  travelMode: MapsTravelMode
  legs: BundleTransportLeg[]
}

export function groupContiguousLegs(legs: BundleTransportLeg[]): ContiguousLegGroup[] {
  return legs.reduce<ContiguousLegGroup[]>((groups, leg) => {
    const travelMode = legTravelMode(leg.mode)
    const current = groups.at(-1)
    const previous = current?.legs.at(-1)
    if (current && previous?.to_place === leg.from_place && current.travelMode === travelMode) {
      current.legs.push(leg)
      return groups
    }
    groups.push({ id: `group-${groups.length + 1}`, travelMode, legs: [leg] })
    return groups
  }, [])
}

interface DailyRouteChunk extends RouteDirectionChunk {
  groupId: string
  travelMode: MapsTravelMode
}

export function buildDailyRouteChunks(bundle: Bundle, legs: BundleTransportLeg[]): DailyRouteChunk[] {
  return groupContiguousLegs(legs).flatMap((group) =>
    buildRouteDirectionChunks(routeStops(bundle, group.legs), group.travelMode).map((chunk) => ({
      ...chunk,
      id: `${group.id}-${chunk.id}`,
      groupId: group.id,
      travelMode: group.travelMode,
    })),
  )
}

function isTransportItem(kind: string): boolean {
  return ['transport', 'car', 'move', 'drive', 'bus', 'train', 'walk', 'walking'].includes(kind.toLowerCase())
}

export function destinationStayMinutes(day: BundleDay, leg: BundleTransportLeg): number | null {
  const linkedIndex = day.items.findIndex((item) => item.transport_leg_id === leg.id)
  const laterItems = linkedIndex >= 0 ? day.items.slice(linkedIndex + 1) : day.items
  const destinationItem = laterItems.find((item) =>
    item.place_id === leg.to_place && !isTransportItem(item.kind) && item.expected_stay_minutes != null,
  )
  return destinationItem?.expected_stay_minutes ?? null
}

export function MapPage({ bundle, route, currentDay }: MapPageProps) {
  const initialDay = [route.day, currentDay].find((candidate) => bundle.days.some((day) => day.date === candidate))
  const [selectedDate, setSelectedDate] = useState(initialDay || bundle.days[0]?.date || '')

  useEffect(() => {
    const next = [route.day, currentDay].find((candidate) => bundle.days.some((day) => day.date === candidate))
    if (next) setSelectedDate(next)
  }, [bundle.days, currentDay, route.day])

  const selectedDay = bundle.days.find((day) => day.date === selectedDate) || bundle.days[0]
  const legs = useMemo(() => selectedDay ? dayLegs(bundle, selectedDay) : [], [bundle, selectedDay])
  const fullRouteChunks = useMemo(() => buildDailyRouteChunks(bundle, legs), [bundle, legs])

  if (!selectedDay) {
    return <section className="map-workspace card">沒有可顯示的日期。</section>
  }

  return (
    <section className="map-workspace" aria-label="地圖與逐段自駕分析">
      <header className="page-intro map-intro">
        <div>
          <p className="eyebrow">ROUTE DESK</p>
          <h1>地圖與逐段交通</h1>
          <p>網站呈現行前規劃估計；按下地圖連結後，以 OpenStreetMap 查找位置與路線。</p>
        </div>
        <div className="map-trust-note"><strong>免費開源</strong><span>只產生 OpenStreetMap 查找連結，不在網站內宣稱即時車程。</span></div>
      </header>

      <nav className="handbook-day-tabs" aria-label="地圖日期切換">
        {bundle.days.map((day, index) => (
          <button
            key={day.date}
            type="button"
            className={day.date === selectedDay.date ? 'is-active' : ''}
            aria-pressed={day.date === selectedDay.date}
            onClick={() => setSelectedDate(day.date)}
          >
            <strong>Day {index + 1}</strong>
            <span>{formatDay(day.date)}</span>
          </button>
        ))}
      </nav>

      <section className="map-day-panel" aria-labelledby={`map-day-${selectedDay.date}`}>
        <header className="map-day-header">
          <div>
            <p className="eyebrow">DAY {bundle.days.indexOf(selectedDay) + 1} · {formatDay(selectedDay.date)}</p>
            <h2 id={`map-day-${selectedDay.date}`}>{selectedDay.summary}</h2>
            <p>{legs.length ? `共 ${legs.length} 段已建模交通，依出發時間排序。` : '此日尚無已建模的逐段交通資料。'}</p>
          </div>
          <div className="daily-route-actions">
            {fullRouteChunks.map((chunk) => (
              <a key={chunk.id} href={chunk.href} target="_blank" rel="noreferrer">
                {fullRouteChunks.length > 1 ? `${transportModeLabel(chunk.travelMode)}：${chunk.sourceLabel} → ${chunk.destinationLabel}` : '開啟今日完整路線'}
              </a>
            ))}
          </div>
        </header>

        {legs.length ? (
          <ol className="route-leg-list">
            {legs.map((leg, index) => {
              const origin = stopFor(bundle, leg.from_place, leg.from_label)
              const destination = stopFor(bundle, leg.to_place, leg.to_label)
              const directionsHref = leg.google_maps_directions_url || buildMapsDirectionsLink([origin, destination], legTravelMode(leg.mode))
              const durationMinutes = leg.transfer_minutes ?? leg.estimated_duration_minutes
              const duration = durationMinutes == null ? '未知，出發前重查' : `${durationMinutes} 分鐘（規劃估計）`
              const buffer = leg.buffer_minutes == null ? '未知，未自行補值' : `${leg.buffer_minutes} 分鐘`
              const stayMinutes = destinationStayMinutes(selectedDay, leg)
              const stay = stayMinutes == null ? '未知，未自行補值' : `${stayMinutes} 分鐘`

              return (
                <li className="route-leg-card" key={leg.id} data-testid={`transport-leg-${leg.id}`}>
                  <div className="route-leg-index" aria-hidden="true">{String(index + 1).padStart(2, '0')}</div>
                  <div className="route-leg-body">
                    <div className="route-leg-topline">
                      <span>{transportModeLabel(leg.mode)}</span>
                      <span className={operationalStatusClass(leg.status)}>{operationalStatusLabel(leg.status)}</span>
                    </div>
                    <div className="route-endpoints">
                      <div><small>起點</small><strong>{leg.from_label || origin.label}</strong></div>
                      <span aria-hidden="true">→</span>
                      <div><small>終點</small><strong>{leg.to_label || destination.label}</strong></div>
                    </div>
                    <dl className="route-leg-facts">
                      <div><dt>規劃時段</dt><dd>{formatTime(leg.departure_at)} → {formatTime(leg.arrival_at)}</dd></div>
                      <div><dt>車程估計</dt><dd>{duration}</dd></div>
                      <div><dt>緩衝</dt><dd>{buffer}</dd></div>
                      <div><dt>目的地停留</dt><dd>{stay}</dd></div>
                      <div><dt>資料狀態</dt><dd>{operationalStatusLabel(leg.status)}</dd></div>
                    </dl>
                    <div className="route-risk-note">
                      <strong>導航注意／延誤切點</strong>
                      <p>{leg.note || '出發前請以 OpenStreetMap 重新確認位置與路線。'}</p>
                    </div>
                    <div className="route-card-actions">
                      <a data-route-url={directionsHref} href={directionsHref} target="_blank" rel="noreferrer">開啟 OpenStreetMap</a>
                      {leg.source_url ? <a className="secondary-link" href={leg.source_url} target="_blank" rel="noreferrer">查看估計來源</a> : null}
                    </div>
                  </div>
                </li>
              )
            })}
          </ol>
        ) : (
          <div className="honest-empty">
            <strong>尚無逐段資料</strong>
            <p>不會把未知車程當成 0 分鐘。請先查看每日行程中的已知停靠點。</p>
          </div>
        )}
      </section>
    </section>
  )
}
