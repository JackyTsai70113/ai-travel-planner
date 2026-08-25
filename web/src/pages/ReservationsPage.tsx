import { useMemo } from 'react'
import {
  Bundle,
  BundleReservation,
} from '../contracts/trip'

interface ReservationsPageProps {
  bundle: Bundle
}

function escapeIcsText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/\r?\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;')
}

function utcCalendarValue(date: Date): string {
  const year = date.getUTCFullYear()
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  const hours = String(date.getUTCHours()).padStart(2, '0')
  const minutes = String(date.getUTCMinutes()).padStart(2, '0')
  const seconds = String(date.getUTCSeconds()).padStart(2, '0')
  return `${year}${month}${day}T${hours}${minutes}${seconds}Z`
}

export function buildReservationCalendarIcs(reservation: BundleReservation): string | null {
  if (!reservation.time || !reservation.name) return null
  const startDate = new Date(reservation.time)
  if (Number.isNaN(startDate.getTime())) return null
  const endDate = new Date(startDate.getTime() + 60 * 60 * 1000)
  return `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//AI Travel Planner//Reservation//ZH-TW
BEGIN:VEVENT
UID:${escapeIcsText(reservation.id)}
DTSTART:${utcCalendarValue(startDate)}
DTEND:${utcCalendarValue(endDate)}
SUMMARY:${escapeIcsText(reservation.name)}
DESCRIPTION:${escapeIcsText(reservation.kind)}
END:VEVENT
END:VCALENDAR`
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
      <header className="page-intro">
        <div><p className="eyebrow">BOOKING DESK</p><h1>預約與固定時間</h1><p>集中查看已排定的日期、時間與集合地點。</p></div>
        <div className="page-intro-stats"><span><strong>{bundle.reservations.length}</strong> 件預約</span></div>
      </header>

      <div className="reservation-groups">
        {grouped.map((group) => (
          <section className="reservation-day" key={group.day}>
            <header><span>{formatDate(group.day)}</span><strong>{group.reservations.length} 件預約</strong></header>
            <div className="reservation-list">
              {group.reservations.map((reservation) => {
                const place = bundle.places?.find((candidate) => candidate.id === reservation.place_id)
                const placeName = place?.name || reservation.name || reservation.place_id
                const address = place?.address
                const mapHref = place?.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place?.maps_query || placeName)}`

                return (
                  <article className="reservation-card" key={reservation.id}>
                    <div className="reservation-time"><strong>{formatTime(reservation.time)}</strong></div>
                    <div className="reservation-main">
                      <div className="reservation-title-row"><h2>{reservation.name || placeName}<a className="reservation-map-link" href={mapHref} target="_blank" rel="noreferrer" aria-label={`${placeName} Google Maps`}>Google Maps ↗</a></h2></div>
                      {address ? <p className="reservation-address">{address}</p> : null}
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
