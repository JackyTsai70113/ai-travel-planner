import { useEffect, useMemo, useState } from 'react'
import { Bundle, BundleDayItem, buildMapsLink, findPlaceAddress, findPlaceLabel } from '../contracts/trip'
import { buildRoutePath, TripRoute } from '../app/route-registry'

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
  if (!value) return '待補'
  return value.match(/T(\d{2}:\d{2})/)?.[1] || value
}

function itemState(item: BundleDayItem, reservationUnresolved: boolean): string[] {
  const states: string[] = []
  if (item.fixed || item.kind === 'reservation' || item.kind === 'flight') states.push('固定')
  if (item.optional || item.kind === 'optional' || item.notes?.toLowerCase().includes('optional')) states.push('可選')
  if (item.cancelable || item.notes?.includes('可取消')) states.push('可取消')
  if (item.unresolved || reservationUnresolved || !item.start_at || !item.end_at) states.push('待補')
  return states.length ? states : ['已確認']
}

function itemVisualKind(item: BundleDayItem, reservationLinked = false): 'reservation' | 'meal' | 'move' | 'place' {
  if (reservationLinked || item.fixed || item.kind === 'reservation' || item.kind === 'flight') return 'reservation'
  if (item.kind === 'meal' || item.kind === 'food') return 'meal'
  if (item.kind === 'transport' || item.kind === 'car' || item.kind === 'move') return 'move'
  return 'place'
}

export function ItineraryPage({ bundle, route, onNavigate }: ItineraryPageProps) {
  const [copiedId, setCopiedId] = useState('')
  const [query, setQuery] = useState('')
  const [plan, setPlan] = useState<'A' | 'B' | 'C'>('A')
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
    const text = [day.date, day.summary, item.notes, place?.name, place?.name_ja, place?.address].filter(Boolean).join(' ').toLowerCase()
    return text.includes(normalizedQuery) ? [{ day, dayIndex, item, label: place?.name || item.place_id }] : []
  })), [bundle.days, bundle.places, normalizedQuery])
  const metrics = {
    places: selectedDay?.items.filter((item) => itemVisualKind(item, !!reservationFor(item)) === 'place').length ?? 0,
    fixed: selectedDay?.items.filter((item) => itemVisualKind(item, !!reservationFor(item)) === 'reservation').length ?? 0,
    unresolved: selectedDay?.items.filter((item) => item.unresolved || reservationFor(item)?.unresolved || !item.start_at || !item.end_at).length ?? 0,
  }
  const alternatives = (bundle.alternatives || []).filter((alternative) => (alternative.plan || 'A') === plan && ['approved', 'ok', 'recommended', 'selected', 'validator-approved'].includes((alternative.status || '').toLowerCase()))

  useEffect(() => {
    if (!route.item) return
    const timer = window.setTimeout(() => document.getElementById(`item-${route.item}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0)
    return () => window.clearTimeout(timer)
  }, [route.item, selectedDay?.date])

  if (!selectedDay) return <section className="card">沒有可顯示的行程日。</section>

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
          <p>依 public bundle 呈現今日順序；固定事項與待補資料會在時間軸中明確標示。</p>
        </div>
        <div className="day-stats" aria-label="今日摘要">
          <span><strong>{selectedDay.items.length}</strong> 停靠</span>
          <span><strong>{metrics.fixed}</strong> 固定</span>
          <span className={metrics.unresolved ? 'has-warning' : ''}><strong>{metrics.unresolved}</strong> 待補</span>
        </div>
      </header>

      {!showPrintView && <div className="itinerary-utility">
        <label className="itinerary-search" htmlFor="itinerary-search">
          <span>搜尋全行程</span>
          <input id="itinerary-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="景點、日文名稱、地址或備註" />
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
          const states = itemState(item, reservation?.unresolved === true)
          const visualKind = itemVisualKind(item, !!reservation)
          const itemCopied = copiedId === `${selectedDay.date}-${item.id}`
          return <article tabIndex={-1} className={`timeline-entry ${visualKind} ${item.id === route.item ? 'item-highlight' : ''}`} id={`item-${item.id}`} key={item.id}>
            <div className="timeline-time"><strong>{timeLabel(item.start_at)}</strong><span>{item.end_at && item.end_at !== item.start_at ? timeLabel(item.end_at) : visualKind === 'reservation' ? '固定' : ''}</span></div>
            <div className="timeline-track"><span>{visualKind === 'reservation' ? '◆' : visualKind === 'meal' ? '✦' : visualKind === 'move' ? '→' : '●'}</span>{index < visibleItems.length - 1 && <i />}</div>
            <div className="timeline-card">
              <div className="timeline-card-topline"><span className="timeline-category">{visualKind === 'reservation' ? '固定預約' : visualKind === 'meal' ? '餐飲安排' : visualKind === 'move' ? '移動 / 緩衝' : '行程停靠'}</span><div className="status-chips">{states.map((state) => <span key={state} className="status-chip">{state}</span>)}</div></div>
              <h3>{findPlaceLabel(bundle.places, item.place_id)}{place?.name_ja ? <small>{place.name_ja}</small> : null}</h3>
              <p className="timeline-detail">{item.notes || (visualKind === 'reservation' ? '此固定事項仍有待確認資訊。' : `停留 ${item.expected_stay_minutes == null ? 'unknown' : `${item.expected_stay_minutes} 分鐘`} · 移動 ${item.transfer_minutes == null ? 'unknown' : `${item.transfer_minutes} 分鐘`}`)}</p>
              {findPlaceAddress(bundle.places, item.place_id) && <p className="timeline-address">{findPlaceAddress(bundle.places, item.place_id)}</p>}
              <div className="timeline-actions">
                <a href={buildMapsLink(place?.maps_query || place?.name || item.place_id)} target="_blank" rel="noreferrer">導航地圖</a>
                <button type="button" onClick={() => copyText(`${selectedDay.date}-${item.id}`, `${findPlaceLabel(bundle.places, item.place_id)} ${findPlaceAddress(bundle.places, item.place_id)}`)}>{itemCopied ? '已複製' : '複製地點'}</button>
                <a href={buildRoutePath({ section: 'today', day: selectedDay.date, item: item.id })}>連結</a>
              </div>
            </div>
          </article>
        })}
        {quickMode !== 'all' && visibleItems.length === 0 && <p className="timeline-empty">目前無法依公開時間資料判斷「{quickMode === 'now' ? '現在' : '下一站'}」。</p>}
      </div>}

      <section className="itinerary-alternatives">
        <div><p className="section-label">ALTERNATIVES</p><h3>Plan A / B / C</h3></div>
        <div className="plan-tabs">{(['A', 'B', 'C'] as const).map((value) => <button key={value} type="button" className={plan === value ? 'active-pill' : ''} onClick={() => setPlan(value)} aria-pressed={plan === value}>Plan {value}</button>)}</div>
        {alternatives.length ? alternatives.map((alternative) => <article key={alternative.id}><strong>{alternative.title}</strong><p>{alternative.summary || '方案內容待補'}</p></article>) : <p className="muted">Plan {plan} unavailable：目前 public bundle 沒有 validator-approved 備案。</p>}
      </section>
    </section>
  )
}
