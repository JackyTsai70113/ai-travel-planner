import { useEffect, useMemo, useState } from 'react'
import { Bundle, BundleDay, BundleDayItem, BundleTransportLeg, buildMapsLink, findPlaceLabel } from '../contracts/trip'
import { TripRoute } from '../app/route-registry'
import { buildMapsDirectionsLink } from '../lib/google-maps-links'
import { AWAJI_DAILY_GUIDE, AWAJI_PLACE_GUIDES, DailyAlternative } from '../content/awaji-travel-guide'

interface ItineraryPageProps {
  bundle: Bundle
  route: TripRoute
  onNavigate: (next: Partial<TripRoute>) => void
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
  if (!value) return '—'
  return value.match(/T(\d{2}:\d{2})/)?.[1] || value
}

function itemVisualKind(item: BundleDayItem, reservationLinked = false): 'reservation' | 'meal' | 'move' | 'place' {
  if (reservationLinked || item.fixed || item.kind === 'reservation' || item.kind === 'flight') return 'reservation'
  if (item.kind === 'meal' || item.kind === 'food') return 'meal'
  if (item.kind === 'transport' || item.kind === 'car' || item.kind === 'move') return 'move'
  return 'place'
}

function transportLegForItem(bundle: Bundle, item: BundleDayItem, dayDate: string): BundleTransportLeg | undefined {
  if (item.transport_leg_id) return bundle.transport_legs?.find((leg) => leg.id === item.transport_leg_id)
  if (itemVisualKind(item) !== 'move') return undefined
  return bundle.transport_legs?.find((leg) =>
    leg.to_place === item.place_id && leg.departure_at?.slice(0, 10) === dayDate &&
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
    .filter((stay) => stay.checkInDate && date >= stay.checkInDate && (!stay.checkOutDate || date <= stay.checkOutDate))
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
  return buildMapsDirectionsLink([
    { id: leg.from_place, label: leg.from_label, mapsQuery: from?.maps_query || from?.address },
    { id: leg.to_place, label: leg.to_label, mapsQuery: to?.maps_query || to?.address },
  ], legTravelMode(leg.mode))
}

export function primaryRiskForDay(_bundle: Bundle, day: BundleDay): string {
  return AWAJI_DAILY_GUIDE[day.date]?.heatRisk || '依當日氣溫安排補水與休息'
}

export function heroNextItem(day: BundleDay, currentMinutes: number | null): BundleDayItem | null {
  if (currentMinutes == null) return day.items[0] || null
  return day.items.find((item) => {
    const start = parseMinutes(item.start_at)
    return start != null && start >= currentMinutes
  }) || null
}

function categoryLabel(kind: ReturnType<typeof itemVisualKind>, item: BundleDayItem): string {
  if (item.kind === 'check_in') return '住宿入住'
  if (item.kind === 'check_out') return '住宿退房'
  if (item.kind === 'free_time') return '行程緩衝'
  if (kind === 'reservation') return item.kind === 'flight' ? '航班' : '固定時間'
  if (kind === 'meal') return '餐飲'
  if (kind === 'move') return '交通'
  return '景點'
}

function movementLabel(mode: string): string {
  if (mode === 'walk' || mode === 'walking') return '步行'
  if (mode === 'bus' || mode === 'train' || mode === 'transit') return '大眾運輸'
  return '開車'
}

function objectiveItemDetail(item: BundleDayItem, leg?: BundleTransportLeg): string {
  if (leg) {
    const minutes = leg.estimated_duration_minutes
    const buffer = leg.buffer_minutes || 0
    return `${movementLabel(leg.mode)}${minutes ? `約 ${minutes} 分鐘` : ''}${buffer ? `；另留 ${buffer} 分鐘供停車與轉場` : ''}`
  }
  if (item.kind === 'flight' && item.notes) return item.notes
  if (item.kind === 'check_in') return '住宿安排已放入今日時間軸。'
  if (item.kind === 'check_out') return '退房後依時間軸前往下一站。'
  if (item.kind === 'free_time') return '保留給報到、休息、用餐或移動的時間。'
  const minutes = item.expected_stay_minutes || (item.start_at && item.end_at ? (parseMinutes(item.end_at) || 0) - (parseMinutes(item.start_at) || 0) : null)
  return minutes && minutes > 0 ? `預計停留 ${minutes} 分鐘` : '依時間軸安排停留。'
}

function Alternatives({ title, items }: { title: string; items: DailyAlternative[] }) {
  return <section className="day-alternative-group"><h3>{title}</h3><div>{items.map((item) => <article key={item.title}><strong>{item.title}</strong><ul>{item.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>)}</div></section>
}

export function ItineraryPage({ bundle, route, onNavigate }: ItineraryPageProps) {
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
    const guide = AWAJI_PLACE_GUIDES[item.place_id]
    const text = [day.date, day.summary, place?.name, leg?.from_label, leg?.to_label, guide?.highlights.join(' ')].filter(Boolean).join(' ').toLowerCase()
    return text.includes(normalizedQuery) ? [{ day, dayIndex, item, label: leg ? `${leg.from_label} → ${leg.to_label}` : place?.name || item.place_id }] : []
  })), [bundle, normalizedQuery])

  useEffect(() => {
    if (!route.item) return
    const timer = window.setTimeout(() => document.getElementById(`item-${route.item}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0)
    return () => window.clearTimeout(timer)
  }, [route.item, selectedDay?.date])

  if (!selectedDay) return <section className="card">沒有可顯示的行程日。</section>

  const guide = AWAJI_DAILY_GUIDE[selectedDay.date]
  const lodging = lodgingForDay(bundle, selectedDay.date)
  const navigateTo = (day: string, item?: string) => onNavigate({ section: 'today', day, item })

  return (
    <section className={`itinerary-workspace ${showPrintView ? 'print-itinerary' : ''}`} aria-label="每日行程">
      <div className="itinerary-day-nav" role="tablist" aria-label="行程日程頁籤">
        <div className="day-nav-label"><span /> 五日導覽</div>
        <div className="day-tabs">{bundle.days.map((day, index) => <button key={day.date} className={`day-tab ${day.date === selectedDay.date ? 'active' : ''}`} role="tab" aria-selected={day.date === selectedDay.date} aria-label={`D${index + 1} ${day.date.slice(5)}`} onClick={() => navigateTo(day.date)} type="button"><strong>D{index + 1}</strong><span>{day.date.slice(5)}</span></button>)}</div>
        <button type="button" className="print-button" onClick={() => setShowPrintView((value) => !value)}>{showPrintView ? '返回行程' : '列印'}</button>
      </div>

      <header className="day-hero">
        <div className="day-kicker"><span>第 {selectedDayIndex + 1} 天</span><span>{selectedDay.date}</span></div>
        <h2>{selectedDay.summary}</h2>
        {guide ? <div className="day-condition-grid" aria-label="當日天候與體力負擔">
          <div><span>天氣與氣溫</span><strong>{guide.temperature}</strong><small>{guide.weather}</small></div>
          <div><span>降雨</span><strong>{guide.rain.split('｜')[0]}</strong><small>{guide.rain.split('｜')[1]}</small></div>
          <div><span>中暑與風浪</span><strong>{guide.heatRisk}</strong><small>{guide.wind}</small></div>
          <div><span>活動量</span><strong>{guide.activity}｜{guide.steps}</strong><small>{guide.stairs}；{guide.slope}</small></div>
          <div><span>開車時間</span><strong>{guide.driving}</strong><small>不含景點停留與用餐</small></div>
          <div><span>固定時間</span><strong>{guide.fixedTimes}</strong><small>其餘停留可依體力調整</small></div>
        </div> : null}
        {lodging ? <div className="day-lodging-card"><span>當晚住宿</span><strong>{lodging.name}</strong>{lodging.official_url ? <a href={lodging.official_url} target="_blank" rel="noreferrer">查看住宿資訊 ↗</a> : null}</div> : null}
        {guide?.tide ? <div className="day-tide-card"><span>鳴門潮流與海況</span><p>{guide.tide}</p><a href="https://www.uzunomichi.jp/tide-calendar/" target="_blank" rel="noreferrer">查看官方潮見表 ↗</a></div> : null}
      </header>

      {!showPrintView ? <div className="itinerary-utility">
        <label className="itinerary-search" htmlFor="itinerary-search"><span>搜尋五日行程</span><input id="itinerary-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜尋景點、餐廳或玩法" /></label>
        <div className="quick-mode" aria-label="行程顯示"><span>顯示：</span>{(['all', 'now', 'next'] as const).map((mode) => <button key={mode} type="button" className={quickMode === mode ? 'active-pill' : ''} aria-pressed={quickMode === mode} onClick={() => setQuickMode(mode)}>{mode === 'all' ? '全部' : mode === 'now' ? '現在' : '下一站'}</button>)}</div>
      </div> : null}

      {normalizedQuery ? <section className="search-results" aria-live="polite"><p>找到 {searchResults.length} 個相符行程</p>{searchResults.map(({ day, dayIndex, item, label }) => <button key={`${day.date}-${item.id}`} type="button" onClick={() => navigateTo(day.date, item.id)}><strong>D{dayIndex + 1}</strong><span>{label}</span><small>{day.date}</small></button>)}</section> : <div className="timeline" aria-label={`${selectedDay.date} 時間軸`}>
        {visibleItems.map((item, index) => {
          const place = bundle.places?.find((candidate) => candidate.id === item.place_id)
          const reservation = reservationFor(item)
          const visualKind = itemVisualKind(item, !!reservation)
          const leg = transportLegForItem(bundle, item, selectedDay.date)
          const title = leg ? `${leg.from_label} → ${leg.to_label}` : findPlaceLabel(bundle.places, item.place_id)
          const mapHref = leg ? legDirectionsLink(bundle, leg) : buildMapsLink(place?.maps_query || place?.name || item.place_id)
          const placeGuide = !leg ? AWAJI_PLACE_GUIDES[item.place_id] : undefined
          const arrivalPlace = leg ? bundle.places?.find((candidate) => candidate.id === leg.to_place) : undefined
          const arrivalParking = leg ? AWAJI_PLACE_GUIDES[leg.to_place]?.parking || arrivalPlace?.parking : undefined
          return <article tabIndex={-1} className={`timeline-entry ${visualKind} ${item.id === route.item ? 'item-highlight' : ''}`} id={`item-${item.id}`} key={item.id}>
            <div className="timeline-time"><strong>{timeLabel(item.start_at)}</strong><span>{item.end_at && item.end_at !== item.start_at ? timeLabel(item.end_at) : ''}</span></div>
            <div className="timeline-track"><span>{visualKind === 'reservation' ? '◆' : visualKind === 'meal' ? '✦' : visualKind === 'move' ? '→' : '●'}</span>{index < visibleItems.length - 1 ? <i /> : null}</div>
            <div className="timeline-card">
              <span className="timeline-category">{categoryLabel(visualKind, item)}</span>
              <h3><a className="timeline-title-link" href={mapHref} target="_blank" rel="noreferrer" aria-label={`${title} 在 Google Maps 開啟`}>{title}<span aria-hidden="true">↗</span></a></h3>
              <p className="timeline-detail">{placeGuide?.duration ? `停留 ${placeGuide.duration}` : objectiveItemDetail(item, leg)}</p>
              {arrivalParking ? <p className="arrival-parking"><strong>抵達與停車</strong>{arrivalParking}</p> : null}
              {placeGuide ? <>
                <dl className="place-facts"><div><dt>費用</dt><dd>{placeGuide.cost}</dd></div><div><dt>排隊</dt><dd>{placeGuide.queue}</dd></div>{placeGuide.hours ? <div><dt>營業時間</dt><dd>{placeGuide.hours}</dd></div> : null}</dl>
                <div className="place-highlights"><strong>{visualKind === 'meal' ? '推薦餐點與飲品' : '值得看與值得玩'}</strong><ul>{placeGuide.highlights.map((highlight) => <li key={highlight}>{highlight}</li>)}</ul></div>
                <a className="official-info-link" href={placeGuide.sourceUrl} target="_blank" rel="noreferrer">官方資訊 ↗</a>
              </> : null}
            </div>
          </article>
        })}
        {quickMode !== 'all' && visibleItems.length === 0 ? <p className="timeline-empty">此日期不是今天，請切回「全部」查看完整行程。</p> : null}
      </div>}

      {guide ? <section className="day-alternatives" aria-label="雨天與額外時間推薦"><Alternatives title="下雨時這樣玩" items={guide.rainOptions} /><Alternatives title="有多的時間，或臨時跳過一站" items={guide.extraTimeOptions} /></section> : null}
    </section>
  )
}
