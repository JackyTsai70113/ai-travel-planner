import { useMemo } from 'react'
import {
  Bundle,
  BundleReservation,
} from '../contracts/trip'
import { buildMapsSearchLink } from '../lib/google-maps-links'

interface ReservationsPageProps {
  bundle: Bundle
}

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat('zh-TW', {
      month: 'numeric',
      day: 'numeric',
      weekday: 'long',
      timeZone: 'Asia/Tokyo',
    }).format(new Date(`${value}T00:00:00+09:00`))
  } catch {
    return value
  }
}

function formatTime(value: string | null) {
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '—'
}

export function ReservationsPage({ bundle }: ReservationsPageProps) {
  const placeGuides = bundle.travel_assistant?.place_guides || {}
  const grouped = useMemo(() => {
    const byDay = new Map<string, BundleReservation[]>()
    bundle.reservations.forEach((reservation) => {
      const current = byDay.get(reservation.day) || []
      byDay.set(reservation.day, [...current, reservation])
    })
    return [...byDay.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([day, reservations]) => ({ day, reservations: reservations.sort((a, b) => (a.time || '').localeCompare(b.time || '')) }))
  }, [bundle.reservations])

  return (
    <section className="reservation-workspace" aria-label="預約與票券">
      <header className="page-intro reservation-intro">
        <div><p className="eyebrow">預約總覽</p><h1>已排定的時間</h1><p>只保留日期、時間、地點與實際會用到的內容；詳細玩法仍放在每日行程。</p></div>
        <div className="page-intro-stats"><span><strong>{bundle.reservations.length}</strong> 筆</span></div>
      </header>

      <div className="reservation-groups">
        {grouped.map((group) => (
          <section className="reservation-day" key={group.day}>
            <header><span>{formatDate(group.day)}</span><strong>{group.reservations.length} 件預約</strong></header>
            <div className="reservation-list">
              {group.reservations.map((reservation) => {
                const place = bundle.places?.find((candidate) => candidate.id === reservation.place_id)
                const placeName = place?.name || reservation.name || reservation.place_id
                const mapHref = buildMapsSearchLink(place?.maps_query || place?.address || placeName)
                const guide = placeGuides[reservation.place_id]

                return (
                  <article className="reservation-card" key={reservation.id}>
                    <div className="reservation-time"><strong>{formatTime(reservation.time)}</strong></div>
                    <div className="reservation-main">
                      <div className="reservation-title-row"><h2><a href={mapHref} target="_blank" rel="noreferrer" aria-label={`${placeName} 在 Google Maps 開啟`}>{reservation.name || placeName}</a></h2></div>
                      {guide ? <p className="reservation-summary">{guide.duration}｜{guide.cost}｜排隊與等候：{guide.queue}</p> : null}
                      {guide ? <ul className="reservation-highlights">{guide.highlights.slice(0, 3).map((highlight) => <li key={highlight}>{highlight}</li>)}</ul> : null}
                      {reservation.official_url || guide?.sourceUrl ? <a className="official-info-link" href={reservation.official_url || guide?.sourceUrl} target="_blank" rel="noreferrer">官方網站</a> : null}
                    </div>
                  </article>
                )
              })}
            </div>
          </section>
        ))}
      </div>

      {bundle.reservations.length === 0 ? <div className="honest-empty"><strong>目前沒有預約紀錄</strong><p>固定行程仍可在每日行程查看。</p><a href="#/today">查看每日行程</a></div> : null}
    </section>
  )
}
