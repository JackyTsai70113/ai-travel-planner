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
  const heroImage = resolveHeroImage(trip)

  const title = trip?.title || bundle?.title || '瀨戶內五日行'
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
          <h1>{title}</h1>
          <p className="trip-hero-route">{destinationText}</p>
          <div className="trip-hero-meta"><span>{dateText}</span><span>{travelersText}</span></div>
          <p className="hero-summary">正在載入五日行程與實用旅遊資訊。</p>
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
  return (
    <section className="trip-overview-shell">
      <article className="trip-overview-hero" style={{ background: heroImage }}>
        <div className="trip-hero-content">
          <h1>{title}</h1>
          <p className="trip-hero-route">{destinationText}</p>
          <div className="trip-hero-meta"><span>{dateText}</span><span>{travelersText}</span></div>
          <p className="hero-summary">從淡路島到德島、神戶，每日時間、天候、體力負擔、餐飲、玩法、住宿與導航都集中在同一條時間軸。</p>
          <div className="hero-actions">
            <a className="primary" href={buildRoutePath({ section: 'today', day: bundle.days[0]?.date })}>查看每日行程</a>
            <a href="#/packing">查看攜帶物品</a>
          </div>
        </div>
      </article>

      <section className="overview-section">
        <div className="section-heading">
          <div><p className="eyebrow">五日行程</p><h2>每天去哪裡，一眼掌握</h2></div>
          <a href="#/today">開啟每日時間軸</a>
        </div>
        <div className="overview-day-grid">
          {bundle.days.map((day, index) => {
            const first = day.items[0]
            const last = day.items.at(-1)
            const lodging = lodgingForDay(bundle, day.date)
            return (
              <a className="overview-day-card" href={buildRoutePath({ section: 'today', day: day.date })} key={day.date}>
                <div className="overview-day-number"><span>DAY</span><strong>{String(index + 1).padStart(2, '0')}</strong></div>
                <div className="overview-day-copy">
                  <p>{formatDay(day.date)} · {day.items.length} 個停靠</p>
                  <h3>{day.summary}</h3>
                  <div className="overview-day-route"><span>{first ? findPlaceLabel(bundle.places, first.place_id) : '—'}</span><i>→</i><span>{last ? findPlaceLabel(bundle.places, last.place_id) : '—'}</span></div>
                  <div className="overview-day-foot"><span>住宿：{lodging?.name || '返程'}</span></div>
                </div>
              </a>
            )
          })}
        </div>
      </section>

      <div className="overview-columns">
        <section className="overview-section">
          <div className="section-heading"><div><p className="eyebrow">住宿安排</p><h2>每天住哪裡</h2></div><a href="#/today">查看每日行程</a></div>
          <div className="overview-stay-list">
            {lodgingCards.map(({ placeId, place, checkIn, checkOut }, index) => (
              <article key={placeId}>
                <span className="stay-sequence">{index + 1}</span>
                <div><p>{checkIn || '—'} → {checkOut || '—'}</p><h3>{place?.name || placeId}</h3></div>
              </article>
            ))}
          </div>
        </section>

        <section className="overview-section">
          <div className="section-heading"><div><p className="eyebrow">固定時間</p><h2>不能錯過的預約與航班</h2></div><a href="#/reservation">查看全部預約</a></div>
          <div className="overview-alert-list">
            {fixedEntries.slice(0, 4).map(({ day, item, label }) => (
              <a href={buildRoutePath({ section: 'today', day, item: item.id })} key={item.id}>
                <strong>{timeLabel(item.start_at)}</strong><span>{label}</span><small>{formatDay(day)}</small>
              </a>
            ))}
            {fixedEntries.length === 0 ? <p className="honest-inline">這趟旅程沒有固定時間。</p> : null}
          </div>
        </section>
      </div>

    </section>
  )
}
