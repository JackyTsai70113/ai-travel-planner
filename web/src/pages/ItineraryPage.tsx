import { useEffect, useMemo, useState } from 'react'
import {
  Bundle,
  BundleDay,
  BundleDayItem,
  BundlePlace,
  BundleProvenance,
  BundleTransportLeg,
  buildMapsLink,
  findPlaceAddress,
  findPlaceLabel,
  operationalStatusClass,
  operationalStatusLabel,
} from '../contracts/trip'
import { buildRoutePath, TripRoute } from '../app/route-registry'
import { buildMapsDirectionsLink } from '../lib/google-maps-links'

interface ItineraryPageProps {
  bundle: Bundle
  route: TripRoute
  onNavigate: (next: Partial<TripRoute>) => void
}

function fieldProvenance(place: BundlePlace, field: 'opening_hours_note' | 'parking'): BundleProvenance | null {
  const direct = place.field_provenance?.[field]
  if (direct) return direct
  const nested = place.provenance
    ? (place.provenance as Record<string, BundleProvenance | null | undefined>)[field]
    : null
  return nested || null
}

function fieldNeedsRecheck(place: BundlePlace, field: 'opening_hours_note' | 'parking'): boolean {
  const provenance = fieldProvenance(place, field)
  const sourceText = [provenance?.provider, provenance?.source_url, provenance?.source_ref, provenance?.note]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  const sheetSourced = sourceText.includes('sheet') || sourceText.includes('docs.google.com/spreadsheets')
  return sheetSourced || (provenance?.status !== 'confirmed' && provenance?.status !== 'user-confirmed')
}
function parseMinutes(value: string | null): number | null {
  const match = value?.match(/(\d{1,2}):(\d{2})/)
  return match ? Number(match[1]) * 60 + Number(match[2]) : null
}

function currentMinutesInTripZone(timeZone: string, dayDate: string): number | null {
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(new Date())
    const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]))
    if (`${values.year}-${values.month}-${values.day}` !== dayDate) return null
    return Number(values.hour) * 60 + Number(values.minute)
  } catch {
    return null
  }
}

function timeLabel(value: string | null): string {
  if (!value) return '待補'
  return value.match(/T(\d{2}:\d{2})/)?.[1] || value
}

function itemState(item: BundleDayItem, reservationUnresolved: boolean, leg?: BundleTransportLeg): string[] {
  const states: string[] = []
  if (item.fixed || item.kind === 'reservation' || item.kind === 'flight') states.push('固定')
  if (item.optional || item.kind === 'optional' || item.notes?.toLowerCase().includes('optional')) states.push('可選')
  if (item.cancelable || item.notes?.includes('可取消')) states.push('可取消')
  if (leg && leg.status !== 'estimated') states.push(operationalStatusLabel(leg.status))
  if (item.unresolved || reservationUnresolved || !item.start_at || !item.end_at) states.push('待補')
  return [...new Set(states.length ? states : ['規劃項目'])]
}

function itemVisualKind(item: BundleDayItem, reservationLinked = false): 'reservation' | 'meal' | 'move' | 'place' {
  if (reservationLinked || item.fixed || item.kind === 'reservation' || item.kind === 'flight') return 'reservation'
  if (item.kind === 'meal' || item.kind === 'food') return 'meal'
  if (item.kind === 'transport' || item.kind === 'car' || item.kind === 'move') return 'move'
  return 'place'
}

function transportLegForItem(bundle: Bundle, item: BundleDayItem, dayDate: string): BundleTransportLeg | undefined {
  if (item.transport_leg_id) {
    return bundle.transport_legs?.find((leg) => leg.id === item.transport_leg_id)
  }
  if (itemVisualKind(item) !== 'move') return undefined
  return bundle.transport_legs?.find((leg) =>
    leg.to_place === item.place_id &&
    leg.departure_at?.slice(0, 10) === dayDate &&
    (!item.start_at || leg.departure_at?.slice(0, 16) === item.start_at.slice(0, 16)),
  )
}

function lodgingForDay(bundle: Bundle, date: string) {
  const allItems = bundle.days.flatMap((day) => day.items)
  const active = bundle.selected.hotel_place_ids
    .map((placeId) => {
      const checkIn = allItems.find((item) => item.kind === 'check_in' && item.place_id === placeId && item.start_at)
      const checkOut = allItems.find((item) => item.kind === 'check_out' && item.place_id === placeId && item.start_at)
      return { placeId, checkInDate: checkIn?.start_at?.slice(0, 10), checkOutDate: checkOut?.start_at?.slice(0, 10) }
    })
    .filter((stay) => stay.checkInDate && date >= stay.checkInDate && (!stay.checkOutDate || date < stay.checkOutDate))
    .sort((a, b) => (b.checkInDate || '').localeCompare(a.checkInDate || ''))[0]
  return bundle.places?.find((place) => place.id === active?.placeId)
}

function legTravelMode(mode: string): 'driving' | 'walking' | 'transit' | 'bicycling' {
  if (mode === 'walk' || mode === 'walking') return 'walking'
  if (mode === 'bus' || mode === 'train' || mode === 'transit') return 'transit'
  if (mode === 'bicycle' || mode === 'bicycling') return 'bicycling'
  return 'driving'
}

function legDirectionsLink(bundle: Bundle, leg: BundleTransportLeg): string {
  const from = bundle.places?.find((place) => place.id === leg.from_place)
  const to = bundle.places?.find((place) => place.id === leg.to_place)
  return leg.google_maps_directions_url || buildMapsDirectionsLink([
    { id: leg.from_place, label: leg.from_label, mapsQuery: from?.maps_query || from?.address },
    { id: leg.to_place, label: leg.to_label, mapsQuery: to?.maps_query || to?.address },
  ], legTravelMode(leg.mode))
}

export function primaryRiskForDay(bundle: Bundle, day: BundleDay): string {
  for (const item of day.items) {
    const leg = transportLegForItem(bundle, item, day.date)
    for (const note of [leg?.note, item.notes]) {
      if (!note) continue
      const delayGate = note.match(/延誤切點[：:]\s*([^；。]+)/)?.[1]?.trim()
      if (delayGate) return delayGate
      if (note.includes('延誤') || note.includes('硬離場') || note.includes('必須上路')) {
        return note.split(/[；。]/)[0].trim()
      }
    }
  }
  return '出發前重查即時路況與當日營運狀態'
}

export function heroNextItem(day: BundleDay, currentMinutes: number | null): BundleDayItem | null {
  if (currentMinutes == null) return day.items[0] || null
  return day.items.find((item) => {
    const start = parseMinutes(item.start_at)
    return start != null && start >= currentMinutes
  }) || null
}

export function ItineraryPage({ bundle, route, onNavigate }: ItineraryPageProps) {
  const [copiedId, setCopiedId] = useState('')
  const [query, setQuery] = useState('')
  const [quickMode, setQuickMode] = useState<'all' | 'now' | 'next'>('all')
  const [showPrintView, setShowPrintView] = useState(false)
  const selectedDay = bundle.days.find((day) => day.date === route.day) ?? (route.day && Number(route.day) > 0 ? bundle.days[Number(route.day) - 1] : undefined) ?? bundle.days[0]
  const selectedDayIndex = bundle.days.findIndex((day) => day.date === selectedDay?.date)
  const currentMinutes = useMemo(() => selectedDay ? currentMinutesInTripZone(bundle.local_timezone, selectedDay.date) : null, [bundle.local_timezone, selectedDay])
  const nowIndex = selectedDay?.items.findIndex((item) => {
    const start = parseMinutes(item.start_at)
    const end = parseMinutes(item.end_at)
    return currentMinutes != null && start != null && end != null && currentMinutes >= start && currentMinutes <= end
  }) ?? -1
  const nextIndex = selectedDay?.items.findIndex((item) => {
    const start = parseMinutes(item.start_at)
    return currentMinutes != null && start != null && start >= currentMinutes
  }) ?? -1
  const visibleItems = selectedDay?.items.filter((_, index) => quickMode === 'now' ? index === nowIndex : quickMode === 'next' ? index === nextIndex : true) ?? []
  const reservationFor = (item: BundleDayItem) => bundle.reservations.find((reservation) => reservation.id === item.id || reservation.itinerary_item_id === item.id)
  const normalizedQuery = query.trim().toLowerCase()
  const searchResults = useMemo(() => !normalizedQuery ? [] : bundle.days.flatMap((day, dayIndex) => day.items.flatMap((item) => {
    const place = bundle.places?.find((candidate) => candidate.id === item.place_id)
    const leg = transportLegForItem(bundle, item, day.date)
    const text = [day.date, day.summary, item.notes, place?.name, place?.name_ja, place?.address, leg?.from_label, leg?.to_label, leg?.note].filter(Boolean).join(' ').toLowerCase()
    return text.includes(normalizedQuery) ? [{ day, dayIndex, item, label: leg ? `${leg.from_label} → ${leg.to_label}` : place?.name || item.place_id }] : []
  })), [bundle, normalizedQuery])
  const metrics = {
    places: selectedDay?.items.filter((item) => itemVisualKind(item, !!reservationFor(item)) === 'place').length ?? 0,
    fixed: selectedDay?.items.filter((item) => itemVisualKind(item, !!reservationFor(item)) === 'reservation').length ?? 0,
    unresolved: selectedDay?.items.filter((item) => item.unresolved || reservationFor(item)?.unresolved || !item.start_at || !item.end_at).length ?? 0,
  }
  useEffect(() => {
    if (!route.item) return
    const timer = window.setTimeout(() => document.getElementById(`item-${route.item}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0)
    return () => window.clearTimeout(timer)
  }, [route.item, selectedDay?.date])

  if (!selectedDay) return <section className="card">沒有可顯示的行程日。</section>

  const nextHeroItem = heroNextItem(selectedDay, currentMinutes)
  const dayFinished = currentMinutes != null && nextHeroItem == null
  const nextHeroLeg = nextHeroItem ? transportLegForItem(bundle, nextHeroItem, selectedDay.date) : undefined
  const lodging = lodgingForDay(bundle, selectedDay.date)
  const fixedEntries = selectedDay.items
    .filter((item) => item.fixed || item.kind === 'reservation' || item.kind === 'flight' || !!reservationFor(item))
    .map((item) => ({ id: item.id, time: timeLabel(item.start_at), label: findPlaceLabel(bundle.places, item.place_id) }))
  const primaryRisk = primaryRiskForDay(bundle, selectedDay)

  const copyText = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(label)
      window.setTimeout(() => setCopiedId((current) => current === label ? '' : current), 1400)
    } catch {
      setCopiedId('error')
    }
  }
  const navigateTo = (day: string, item?: string) => onNavigate({ section: 'today', day, item })

  return (
    <section className={`itinerary-workspace ${showPrintView ? 'print-itinerary' : ''}`} aria-label="每日行程工作區">
      <div className="itinerary-day-nav" role="tablist" aria-label="行程日程頁籤">
        <div className="day-nav-label"><span /> 五日導覽</div>
        <div className="day-tabs">
          {bundle.days.map((day, index) => (
            <button key={day.date} className={`day-tab ${day.date === selectedDay.date ? 'active' : ''}`} role="tab" aria-selected={day.date === selectedDay.date} onClick={() => navigateTo(day.date)} type="button">
              <strong>D{index + 1}</strong><span>{day.date.slice(5)}</span>
            </button>
          ))}
        </div>
        <button type="button" className="print-button" onClick={() => setShowPrintView((value) => !value)}>{showPrintView ? '返回操作模式' : '列印'}</button>
      </div>

      <header className="day-hero">
        <div className="day-hero-copy">
          <div className="day-kicker"><span>DAY {selectedDayIndex + 1}</span><span>{selectedDay.date}</span></div>
          <h2>{selectedDay.summary}</h2>
          <div className="day-answer-grid" aria-label="今日快速摘要">
            <div><span>下一站</span><strong>{dayFinished ? '今日行程已結束' : nextHeroLeg ? nextHeroLeg.to_label : nextHeroItem ? findPlaceLabel(bundle.places, nextHeroItem.place_id) : '今日無停靠'}</strong><small>{dayFinished ? '請休息並確認明日安排' : nextHeroItem ? timeLabel(nextHeroItem.start_at) : '—'}</small></div>
            <div><span>今晚住宿</span><strong>{lodging?.name || '返程／尚無當晚住宿'}</strong><small>{lodging?.address || '以當日行程為準'}</small></div>
            <div><span>固定時間</span><strong>{fixedEntries.length ? fixedEntries.map((entry) => entry.time).join('、') : '今日無固定預約'}</strong><small>{fixedEntries.map((entry) => entry.label).join('、') || '保留彈性'}</small></div>
            <div><span>主要風險</span><strong>{primaryRisk}</strong><small>營業、天候與即時路況於出發前確認</small></div>
          </div>
        </div>
        <div className="day-stats" aria-label="今日摘要數量">
          <span><strong>{selectedDay.items.length}</strong> 停靠</span>
          <span><strong>{metrics.fixed}</strong> 固定</span>
          <span className={metrics.unresolved ? 'has-warning' : ''}><strong>{metrics.unresolved}</strong> 待補</span>
        </div>
      </header>

      {!showPrintView && <div className="itinerary-utility">
        <label className="itinerary-search" htmlFor="itinerary-search">
          <span>搜尋五日行程</span>
          <input id="itinerary-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="景點、日文名稱、地址、起訖或提醒" />
        </label>
        <div className="quick-mode" aria-label="現場快速模式">
          <span>顯示：</span>
          {(['all', 'now', 'next'] as const).map((mode) => <button key={mode} type="button" className={quickMode === mode ? 'active-pill' : ''} aria-pressed={quickMode === mode} onClick={() => setQuickMode(mode)}>{mode === 'all' ? '全部' : mode === 'now' ? '現在' : '下一站'}</button>)}
        </div>
      </div>}

      {normalizedQuery ? <section className="search-results" aria-live="polite">
        <p>找到 {searchResults.length} 個相符行程</p>
        {searchResults.map(({ day, dayIndex, item, label }) => <button key={`${day.date}-${item.id}`} type="button" onClick={() => navigateTo(day.date, item.id)}><strong>D{dayIndex + 1}</strong><span>{label}</span><small>{day.date}</small></button>)}
      </section> : <div className="timeline" aria-label={`${selectedDay.date} 時間軸`}>
        {visibleItems.map((item, index) => {
          const place = bundle.places?.find((candidate) => candidate.id === item.place_id)
          const reservation = reservationFor(item)
          const visualKind = itemVisualKind(item, !!reservation)
          const leg = transportLegForItem(bundle, item, selectedDay.date)
          const states = itemState(item, reservation?.unresolved === true, leg)
          const itemCopied = copiedId === `${selectedDay.date}-${item.id}`
          const title = leg ? `${leg.from_label} → ${leg.to_label}` : findPlaceLabel(bundle.places, item.place_id)
          const detail = leg
            ? `${leg.estimated_duration_minutes == null ? '車程尚未確認' : `約 ${leg.estimated_duration_minutes} 分鐘`} · ${leg.note || '尚無專屬導航提醒'}`
            : item.notes || `停留 ${item.expected_stay_minutes == null ? '尚未提供' : `${item.expected_stay_minutes} 分鐘`} · 前段移動 ${item.transfer_minutes == null ? '尚未提供' : `${item.transfer_minutes} 分鐘`}`
          const mapsHref = leg ? legDirectionsLink(bundle, leg) : place?.google_maps_url || buildMapsLink(place?.maps_query || place?.name || item.place_id)
          const copyValue = leg ? `${leg.from_label} → ${leg.to_label}` : `${title} ${findPlaceAddress(bundle.places, item.place_id)}`
          const itemAlternatives = (item.alternative_place_ids || [])
            .map((placeId) => bundle.places?.find((candidate) => candidate.id === placeId))
            .filter((candidate): candidate is BundlePlace => !!candidate)

          return <article tabIndex={-1} className={`timeline-entry ${visualKind} ${item.id === route.item ? 'item-highlight' : ''}`} id={`item-${item.id}`} key={item.id}>
            <div className="timeline-time"><strong>{timeLabel(item.start_at)}</strong><span>{item.end_at && item.end_at !== item.start_at ? timeLabel(item.end_at) : visualKind === 'reservation' ? '固定' : ''}</span></div>
            <div className="timeline-track"><span>{visualKind === 'reservation' ? '◆' : visualKind === 'meal' ? '✦' : visualKind === 'move' ? '→' : '●'}</span>{index < visibleItems.length - 1 && <i />}</div>
            <div className="timeline-card">
              <div className="timeline-card-topline"><span className="timeline-category">{visualKind === 'reservation' ? '固定預約' : visualKind === 'meal' ? '餐飲安排' : visualKind === 'move' ? '逐段交通' : '行程停靠'}</span><div className="status-chips">{states.map((state) => <span key={state} className="status-chip">{state}</span>)}</div></div>
              <h3>{title}{!leg && place?.name_ja ? <small>{place.name_ja}</small> : null}</h3>
              <p className="timeline-detail">{detail}</p>
              {!leg && findPlaceAddress(bundle.places, item.place_id) && <p className="timeline-address">{findPlaceAddress(bundle.places, item.place_id)}</p>}
              {leg ? <div className="timeline-risk"><span className={operationalStatusClass(leg.status)}>{operationalStatusLabel(leg.status)}</span><p><strong>風險／延誤切點：</strong>{leg.note || '未提供；出發前以 Google Maps 即時路況確認。'}</p></div> : null}
              {!leg && place?.opening_hours_note ? <p className={`timeline-context ${fieldNeedsRecheck(place, 'opening_hours_note') ? 'needs-recheck' : ''}`}><strong>營業時間：</strong>{place.opening_hours_note}</p> : null}
              {!leg && place?.parking ? <p className={`timeline-context ${fieldNeedsRecheck(place, 'parking') ? 'needs-recheck' : ''}`}><strong>停車：</strong>{place.parking}</p> : null}
              {place?.accessibility_notes ? <p className="timeline-context"><strong>家庭／無障礙：</strong>{place.accessibility_notes}</p> : null}
              {!leg && itemAlternatives.length ? <div className="timeline-inline-alternatives"><strong>試算表備案：</strong>{itemAlternatives.map((alternative) => <a key={alternative.id} href={alternative.google_maps_url || buildMapsLink(alternative.maps_query || alternative.address || alternative.name || alternative.id)} target="_blank" rel="noreferrer">{alternative.name || alternative.id}</a>)}</div> : null}
              <div className="timeline-actions">
                <a href={mapsHref} target="_blank" rel="noreferrer">{leg ? '逐段導航' : '導航地圖'}</a>
                <button type="button" onClick={() => copyText(`${selectedDay.date}-${item.id}`, copyValue)}>{itemCopied ? '已複製' : '複製地點'}</button>
                <a href={buildRoutePath({ section: 'today', day: selectedDay.date, item: item.id })}>分享連結</a>
              </div>
            </div>
          </article>
        })}
        {quickMode !== 'all' && visibleItems.length === 0 && <p className="timeline-empty">目前無法依已知時間判斷「{quickMode === 'now' ? '現在' : '下一站'}」。</p>}
      </div>}

    </section>
  )
}
