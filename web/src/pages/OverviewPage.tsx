import {
  Bundle,
  findPlaceLabel,
} from '../contracts/trip'
import type { TripCatalogEntry } from '../contracts/trip-registry'
import { buildRoutePath } from '../app/route-registry'

interface OverviewPageProps {
  bundle: Bundle | null
  trip: TripCatalogEntry | null
}
function resolveHeroImage(trip: TripCatalogEntry | null): string {
  if (trip?.cover_media.kind === 'image' && trip.cover_media.url) {
    return `linear-gradient(115deg, rgba(5, 25, 39, 0.9), rgba(5, 55, 72, 0.54)), url(${trip.cover_media.url}) center/cover no-repeat`
  }
  return trip?.cover_media.gradient || 'linear-gradient(125deg, #0b2638 0%, #0c6574 72%, #3ea69c 140%)'
}

function formatDay(date: string, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat('zh-TW', {
      month: 'numeric',
      day: 'numeric',
      weekday: 'short',
      timeZone,
    }).format(new Date(`${date}T12:00:00Z`))
  } catch {
    return date
  }
}

function timeLabel(value: string | null): string {
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '—'
}

function dayCountLabel(days: number): string {
  const numerals = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
  return `${numerals[days] || String(days)}日`
}

function fixedLabel(item: { kind: string; notes?: string }, fallback: string): string {
  if (item.kind === 'flight') return item.notes?.match(/JX\d{3,4}/)?.[0] || '航班'
  return fallback
}

export function OverviewPage({ bundle, trip }: OverviewPageProps) {
  const heroImage = resolveHeroImage(trip)

  const title = trip?.title || bundle?.title || '旅行行程'
  const routeStops = trip?.destination_regions.length
    ? trip.destination_regions
    : bundle?.overview?.trip_scope || []
  const heroEyebrow = routeStops.length > 0 ? `${routeStops[0]}旅行` : '旅行行程'
  const heroSummary = trip?.hero_summary || `${routeStops.join('、')}的每日行程、餐飲、住宿與導航資訊。`
  const dateText = trip
    ? `${trip.date_range.start_date} — ${trip.date_range.end_date} · ${trip.duration_days} 天`
    : bundle ? `${bundle.date_range.start_date} — ${bundle.date_range.end_date} · ${bundle.days.length} 天` : '行程資料載入中'
  if (!bundle) {
    return (
      <section className="trip-overview-shell">
        <article className="trip-overview-hero" style={{ background: heroImage }}>
          <div className="trip-hero-content">
            <p className="trip-hero-eyebrow">{heroEyebrow}</p>
            <h1>{title}</h1>
            <div className="trip-hero-meta"><span>{dateText}</span></div>
            <p className="hero-summary">{heroSummary}</p>
          </div>
        </article>
      </section>
    )
  }

  const lodgingCards = bundle.selected.hotel_place_ids.map((placeId) => {
    const place = bundle.places?.find((candidate) => candidate.id === placeId)
    const allItems = bundle.days.flatMap((day) => day.items)
    const checkIn = allItems.find((item) => item.kind === 'check_in' && item.place_id === placeId)
    const checkOut = allItems.find((item) => item.kind === 'check_out' && item.place_id === placeId)
    return { placeId, place, checkIn: checkIn?.start_at?.slice(0, 10), explicitCheckOut: checkOut?.start_at?.slice(0, 10) }
  }).sort((a, b) => (a.checkIn || '').localeCompare(b.checkIn || '')).map((stay, index, stays) => ({
    ...stay,
    checkOut: stay.explicitCheckOut || stays[index + 1]?.checkIn,
  }))
  const fixedEntries = bundle.days.flatMap((day) => day.items
    .filter((item) => item.fixed || item.kind === 'reservation' || item.kind === 'flight' || bundle.reservations.some((reservation) => reservation.id === item.id || reservation.itinerary_item_id === item.id))
    .map((item) => ({ day: day.date, item, label: fixedLabel(item, findPlaceLabel(bundle.places, item.place_id)) })))
  const dayCount = bundle.days.length
  const pretripChecklist = bundle.operations?.pretrip_checklist || []
  const sourceLedger = (bundle.source_ledger || []).filter((source) => source.source_url).slice(0, 8)
  const hotelCandidates = bundle.hotel_candidates || []
  return (
    <section className="trip-overview-shell">
      <article className="trip-overview-hero" style={{ background: heroImage }}>
        <div className="trip-hero-content">
          <p className="trip-hero-eyebrow">{heroEyebrow}</p>
          <h1>{title}</h1>
          <div className="trip-hero-meta"><span>{dateText}</span></div>
          {trip?.status === 'preview' || trip?.readiness === 'incomplete' ? <p className="status-pill">{bundle?.presentation?.preview_notice || '預覽行程：住宿訂房與必要交通仍待確認，請完成下方覆核後再出發。'}</p> : null}
          <p className="hero-summary">{heroSummary}</p>
        </div>
        <aside className="hero-route-map" aria-label={`${dayCountLabel(dayCount)}移動路線：${routeStops.join('、')}`}>
          <p>{dayCountLabel(dayCount)}移動路線</p>
          <ol>{routeStops.map((stop, index) => <li key={stop}><span>{index + 1}</span><strong>{stop}</strong></li>)}</ol>
        </aside>
      </article>

      <section className="overview-section">
        <div className="section-heading">
          <div><p className="eyebrow">{dayCountLabel(dayCount)}行程</p><h2>每天去哪裡，一眼掌握</h2></div>
        </div>
        <div className="overview-day-grid">
          {bundle.days.map((day, index) => {
            const first = day.items[0]
            const last = day.items.at(-1)
            return (
              <a className="overview-day-card" href={buildRoutePath({ section: 'today', day: day.date })} key={day.date}>
                <div className="overview-day-number"><span>DAY</span><strong>{String(index + 1).padStart(2, '0')}</strong></div>
                <div className="overview-day-copy">
                  <p>{formatDay(day.date, bundle.local_timezone)} · {day.items.length} 個停靠</p>
                  <h3>{day.summary}</h3>
                  <div className="overview-day-route"><span>{first ? findPlaceLabel(bundle.places, first.place_id) : '—'}</span><i>→</i><span>{last ? findPlaceLabel(bundle.places, last.place_id) : '—'}</span></div>
                </div>
              </a>
            )
          })}
        </div>
      </section>

      <div className="overview-columns">
        <section className="overview-section">
          <div className="section-heading"><div><p className="eyebrow">住宿首選</p><h2>尚未訂房的行程落點</h2></div></div>
          <div className="overview-stay-list">
            {lodgingCards.map(({ placeId, place, checkIn, checkOut }, index) => (
              <article key={placeId}>
                <span className="stay-sequence">{index + 1}</span>
                <div><p>{checkIn || '—'} → {checkOut || '—'}</p><h3>{place?.name || placeId}</h3>{place?.opening_hours_note ? <small>{place.opening_hours_note}</small> : null}{place?.official_url ? <a href={place.official_url} target="_blank" rel="noreferrer">官方訂房／資訊</a> : null}</div>
              </article>
            ))}
          </div>
        </section>

        <section className="overview-section">
          <div className="section-heading"><div><p className="eyebrow">固定時間</p><h2>不能錯過的預約與航班</h2></div></div>
          <div className="overview-alert-list">
            {fixedEntries.slice(0, 4).map(({ day, item, label }) => (
              <a href={buildRoutePath({ section: 'today', day, item: item.id })} key={item.id}>
                <strong>{timeLabel(item.start_at)}</strong><span>{label}</span><small>{formatDay(day, bundle.local_timezone)}</small>
              </a>
            ))}
            {fixedEntries.length === 0 ? <p className="honest-inline">這趟旅程沒有固定時間。</p> : null}
          </div>
        </section>
      </div>

      {hotelCandidates.length > 0 ? <section className="overview-section" aria-labelledby="hotel-candidates-title">
          <div className="section-heading"><div><p className="eyebrow">住宿評估</p><h2 id="hotel-candidates-title">河景房必須符合：兩晚含稅不超過 NT$6,000</h2></div></div>
        <p className="overview-candidate-intro">以下 5 間均以 Agoda 的 2026/09/30 入住、10/02 退房、1 位成人查房連結整理，尚未代訂。只有結帳頁明列「河景／河畔景觀」房型、可取消條款符合需求，且兩晚含稅總額不超過 NT$6,000，才可選為住宿；公開頁未回傳動態總價時，一律標示待確認。</p>
        <div className="overview-candidate-grid">
          {hotelCandidates.map((candidate, index) => <article className="overview-candidate-card" key={candidate.place_id}>
            <div className="overview-candidate-topline"><span>候選 {index + 1}</span>{candidate.selected_candidate ? <strong>已符合條件</strong> : candidate.price_status === 'unverified' ? <strong>條件待確認</strong> : <strong>備選</strong>}</div>
            <h3>{candidate.name}</h3>
            {candidate.room_type ? <p className="overview-candidate-room">房型線索：{candidate.room_type}</p> : null}
            <p>{candidate.decision_note || '請以訂房頁的房型、取消條款與入住規則為準。'}</p>
            {candidate.distance_notes?.length ? <div className="overview-candidate-distance"><strong>距離與夜景判斷：</strong><ul>{candidate.distance_notes.map((note) => <li key={note}>{note}</li>)}</ul></div> : null}
            {candidate.price_note ? <p className="overview-candidate-price"><strong>價格／查核：</strong>{candidate.price_note}</p> : null}
            <p className="overview-candidate-status">價格狀態：{candidate.price_status === 'unverified' ? '需以一成人結帳頁確認' : candidate.price_status || '未確認'}</p>
            <div className="overview-candidate-actions">
              {candidate.search_url ? <a href={candidate.search_url} target="_blank" rel="noreferrer">查房／訂房</a> : null}
              {candidate.official_url ? <a href={candidate.official_url} target="_blank" rel="noreferrer">官方資訊</a> : null}
              {candidate.google_maps_url ? <a href={candidate.google_maps_url} target="_blank" rel="noreferrer">查看位置</a> : null}
            </div>
          </article>)}
        </div>
      </section> : null}

      {(pretripChecklist.length > 0 || sourceLedger.length > 0) ? <div className="overview-columns">
        {pretripChecklist.length > 0 ? <section className="overview-section">
          <div className="section-heading"><div><p className="eyebrow">出發前覆核</p><h2>尚未代你完成的事項</h2></div></div>
          <div className="overview-alert-list">{pretripChecklist.map((item) => <article key={item.id}><strong>{item.timing || '出發前'}</strong><span>{item.item}</span><small>{item.action}{item.fallback ? `；備案：${item.fallback}` : ''}</small></article>)}</div>
        </section> : null}
        {sourceLedger.length > 0 ? <section className="overview-section">
          <div className="section-heading"><div><p className="eyebrow">來源與更新</p><h2>開放與交通以官方資訊為準</h2></div></div>
          <div className="overview-alert-list">{sourceLedger.map((source, index) => <a href={source.source_url || '#'} target="_blank" rel="noreferrer" key={`${source.source_url}-${index}`}><strong>{source.authority || '來源'}</strong><span>{Array.isArray(source.supports) ? source.supports.join('、') : source.supports || '行程資訊'}</span><small>{source.last_checked ? `最後查核：${source.last_checked}` : '出發前請再覆核'}</small></a>)}</div>
        </section> : null}
      </div> : null}

    </section>
  )
}
