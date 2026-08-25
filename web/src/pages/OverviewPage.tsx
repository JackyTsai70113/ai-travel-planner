import {
  Bundle,
  findPlaceLabel,
  formatMoney,
  toFriendlyStatus,
} from '../contracts/trip'
import type { TripCatalogEntry } from '../contracts/trip-registry'
import { buildRoutePath } from '../app/route-registry'

interface OverviewPageProps {
  bundle: Bundle | null
  trip: TripCatalogEntry | null
}
function resolveStatusBadge(readiness: TripCatalogEntry['readiness']): { className: string; text: string } {
  if (readiness === 'ready') return { className: 'status-pill status-ready', text: '可出發' }
  if (readiness === 'incomplete') return { className: 'status-pill status-incomplete', text: '行前需確認' }
  return { className: 'status-pill status-blocked', text: '有關鍵阻斷' }
}

function resolvePublicationBadge(status: TripCatalogEntry['status']): { className: string; text: string } {
  if (status === 'published') return { className: 'status-pill status-published', text: '正式版本' }
  if (status === 'preview') return { className: 'status-pill status-preview', text: '預覽版本' }
  return { className: 'status-pill status-archived', text: '封存版本' }
}

function resolveHeroImage(trip: TripCatalogEntry | null): string {
  if (trip?.cover_media.kind === 'image' && trip.cover_media.url) {
    return `linear-gradient(115deg, rgba(5, 25, 39, 0.9), rgba(5, 55, 72, 0.54)), url(${trip.cover_media.url}) center/cover no-repeat`
  }
  return trip?.cover_media.gradient || 'linear-gradient(125deg, #0b2638 0%, #0c6574 72%, #3ea69c 140%)'
}

function resolveCriticalCount(bundle: Bundle | null, trip: TripCatalogEntry | null): number {
  if (!bundle) return trip?.critical_alert_count || 0
  const unresolvedReservations = bundle.reservations.filter((item) => item.unresolved).length
  return bundle.validation.filter((item) => item.severity === 'error' || item.severity === 'warning').length + unresolvedReservations
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

function timeLabel(value: string | null): string {
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '—'
}

function fixedLabel(item: { kind: string; notes?: string }, fallback: string): string {
  if (item.kind === 'flight') return item.notes?.match(/JX\d{3,4}/)?.[0] || '航班'
  return fallback
}

function lodgingForDay(bundle: Bundle, date: string) {
  const items = bundle.days.flatMap((day) => day.items)
  const active = bundle.selected.hotel_place_ids
    .map((placeId) => {
      const checkIn = items.find((item) => item.kind === 'check_in' && item.place_id === placeId && item.start_at)
      const checkOut = items.find((item) => item.kind === 'check_out' && item.place_id === placeId && item.start_at)
      return { placeId, checkInDate: checkIn?.start_at?.slice(0, 10), checkOutDate: checkOut?.start_at?.slice(0, 10) }
    })
    .filter((stay) => stay.checkInDate && date >= stay.checkInDate && (!stay.checkOutDate || date < stay.checkOutDate))
    .sort((a, b) => (b.checkInDate || '').localeCompare(a.checkInDate || ''))[0]
  return bundle.places?.find((place) => place.id === active?.placeId)
}

export function OverviewPage({ bundle, trip }: OverviewPageProps) {
  const publication = resolvePublicationBadge(trip?.status || 'preview')
  const readiness = resolveStatusBadge(trip?.readiness || 'incomplete')
  const heroImage = resolveHeroImage(trip)
  const criticalCount = resolveCriticalCount(bundle, trip)

  const title = trip?.title || bundle?.title || '旅行手冊'
  const destinationText = trip?.destination_regions.join(' / ') || '淡路島・德島・神戶'
  const dateText = trip
    ? `${trip.date_range.start_date} — ${trip.date_range.end_date} · ${trip.duration_days} 天`
    : bundle ? `${bundle.date_range.start_date} — ${bundle.date_range.end_date} · ${bundle.days.length} 天` : '行程資料載入中'
  const travelersText = bundle
    ? `${bundle.traveler_profile.adults} 大 ${bundle.traveler_profile.children_count} 小`
    : trip?.travelers_summary || '旅客資料載入中'

  if (!bundle) {
    return (
      <section className="trip-overview-shell">
        <article className="trip-overview-hero" style={{ background: heroImage }}>
          <p className="trip-hero-eyebrow">SETOUCHI TRAVEL HANDBOOK</p>
          <h1>{title}</h1>
          <p className="trip-hero-route">{destinationText}</p>
          <div className="trip-hero-meta"><span>{dateText}</span><span>{travelersText}</span></div>
          <p className="hero-summary">{trip?.hero_summary || '正在載入 Canonical Trip；完成後會顯示五日路線與操作資訊。'}</p>
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
  const validationAlerts = bundle.validation.filter((item) => item.severity === 'error' || item.severity === 'warning')

  return (
    <section className="trip-overview-shell">
      <article className="trip-overview-hero" style={{ background: heroImage }}>
        <div className="trip-hero-content">
          <p className="trip-hero-eyebrow">SETOUCHI TRAVEL HANDBOOK</p>
          <h1>{title}</h1>
          <p className="trip-hero-route">{destinationText}</p>
          <div className="trip-hero-meta"><span>{dateText}</span><span>{travelersText}</span></div>
          <p className="hero-summary">{trip?.hero_summary || '從淡路島到德島、神戶，把每日時間、住宿、導航與行前確認放在同一本手冊。'}</p>
          <div className="hero-tags">
            <span className={publication.className}>{publication.text}</span>
            <span className={readiness.className}>{readiness.text}</span>
            <span className="status-pill status-warning">{criticalCount} 則提醒</span>
          </div>
          <div className="hero-actions">
            <a className="primary" href={buildRoutePath({ section: 'today', day: bundle.days[0]?.date })}>開始 Day 1</a>
            <a href="#/today">每日自駕與導航</a>
            <a href="#/packing">出發前清單</a>
          </div>
        </div>
        <aside className="hero-brief" aria-label="旅行摘要">
          <p>TRIP SNAPSHOT</p>
          <dl>
            <div><dt>狀態</dt><dd>{toFriendlyStatus(bundle.status)}</dd></div>
            <div><dt>天數</dt><dd>{bundle.days.length} 日</dd></div>
            <div><dt>住宿</dt><dd>{lodgingCards.length} 處</dd></div>
            <div><dt>逐段交通</dt><dd>{bundle.transport_legs?.length || 0} 段</dd></div>
          </dl>
        </aside>
      </article>

      <section className="overview-section">
        <div className="section-heading">
          <div><p className="eyebrow">FIVE DAY PLAN</p><h2>五日路線一眼掌握</h2></div>
          <a href="#/today">開啟每日時間軸</a>
        </div>
        <div className="overview-day-grid">
          {bundle.days.map((day, index) => {
            const first = day.items[0]
            const last = day.items.at(-1)
            const lodging = lodgingForDay(bundle, day.date)
            const fixedCount = fixedEntries.filter((entry) => entry.day === day.date).length
            return (
              <a className="overview-day-card" href={buildRoutePath({ section: 'today', day: day.date })} key={day.date}>
                <div className="overview-day-number"><span>DAY</span><strong>{String(index + 1).padStart(2, '0')}</strong></div>
                <div className="overview-day-copy">
                  <p>{formatDay(day.date)} · {day.items.length} 個停靠</p>
                  <h3>{day.summary}</h3>
                  <div className="overview-day-route"><span>{first ? findPlaceLabel(bundle.places, first.place_id) : '—'}</span><i>→</i><span>{last ? findPlaceLabel(bundle.places, last.place_id) : '—'}</span></div>
                  <div className="overview-day-foot"><span>住宿：{lodging?.name || '返程／未安排'}</span><span>固定 {fixedCount} 項</span></div>
                </div>
              </a>
            )
          })}
        </div>
      </section>

      <div className="overview-columns">
        <section className="overview-section">
          <div className="section-heading"><div><p className="eyebrow">STAYS</p><h2>住宿接力</h2></div><a href="#/lodging">住宿詳情</a></div>
          <div className="overview-stay-list">
            {lodgingCards.map(({ placeId, place, checkIn, checkOut }, index) => (
              <article key={placeId}>
                <span className="stay-sequence">{index + 1}</span>
                <div><p>{checkIn || '—'} → {checkOut || '—'}</p><h3>{place?.name || placeId}</h3>{place?.address ? <small>{place.address}</small> : null}</div>
              </article>
            ))}
          </div>
        </section>

        <section className="overview-section">
          <div className="section-heading"><div><p className="eyebrow">FIXED & TRUST</p><h2>固定時間與提醒</h2></div><a href="#/reservation">預約詳情</a></div>
          <div className="overview-alert-list">
            {fixedEntries.slice(0, 4).map(({ day, item, label }) => (
              <a href={buildRoutePath({ section: 'today', day, item: item.id })} key={item.id}>
                <strong>{timeLabel(item.start_at)}</strong><span>{label}</span><small>{formatDay(day)}</small>
              </a>
            ))}
            {fixedEntries.length === 0 ? <p className="honest-inline">目前沒有標記為固定的時間項目。</p> : null}
            {validationAlerts.slice(0, 3).map((alert) => <div className="overview-warning" key={alert.code}><strong>{alert.severity}</strong><span>{alert.message}</span></div>)}
          </div>
        </section>
      </div>

      <footer className="overview-footer">
        <span>預算快照：{formatMoney(bundle.budget?.total)}</span>
        <span>Google Maps 即時交通以開啟導航當下為準</span>
      </footer>
    </section>
  )
}
