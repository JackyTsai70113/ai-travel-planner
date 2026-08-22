import { useMemo, useState } from 'react'
import {
  Bundle,
  BundleReservation,
  operationalStatusClass,
  operationalStatusLabel,
} from '../contracts/trip'
import { buildRoutePath } from '../app/route-registry'

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
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '時間未提供'
}

function resolveReservationStatus(reservation: BundleReservation) {
  if (reservation.unresolved) return 'unresolved' as const
  if (reservation.status) return reservation.status
  if (reservation.time && reservation.name) return 'confirmed' as const
  if (reservation.time || reservation.name) return 'estimated' as const
  return 'unverified' as const
}

function buildDayItemLink(bundle: Bundle, reservation: BundleReservation) {
  const day = bundle.days.find((itemDay) => itemDay.date === reservation.day) ?? bundle.days[0]
  if (!day) return buildRoutePath({ section: 'today' })
  const direct = day.items.find((item) => item.id === reservation.id || item.id === reservation.itinerary_item_id)
  if (direct) return buildRoutePath({ section: 'today', day: day.date, item: direct.id })
  return buildRoutePath({ section: 'today', day: day.date })
}

export function ReservationsPage({ bundle }: ReservationsPageProps) {
  const [copying, setCopying] = useState('')
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

  const statuses = bundle.reservations.map(resolveReservationStatus)
  const confirmedCount = statuses.filter((status) => status === 'confirmed').length
  const pendingCount = statuses.filter((status) => status !== 'confirmed').length

  const copyText = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopying(key)
      window.setTimeout(() => setCopying(''), 1500)
    } catch {
      setCopying('error')
    }
  }

  return (
    <section className="reservation-workspace" aria-label="預約與票券">
      <header className="page-intro">
        <div><p className="eyebrow">BOOKING DESK</p><h1>預約與固定時間</h1><p>把日期、時間、地址、聯絡方式與當日行程集中在同一處；未知欄位維持未確認。</p></div>
        <div className="page-intro-stats"><span><strong>{bundle.reservations.length}</strong> 件</span><span><strong>{confirmedCount}</strong> 已確認</span><span className={pendingCount ? 'has-warning' : ''}><strong>{pendingCount}</strong> 待處理</span></div>
      </header>

      {pendingCount ? <div className="reservation-alert"><strong>出發前仍需確認</strong><p>{pendingCount} 件資料含未驗證或未補齊欄位。使用官方連結或電話確認後，再以最新資訊為準。</p></div> : null}

      <div className="reservation-groups">
        {grouped.map((group) => (
          <section className="reservation-day" key={group.day}>
            <header><span>{formatDate(group.day)}</span><strong>{group.reservations.length} 件預約</strong></header>
            <div className="reservation-list">
              {group.reservations.map((reservation) => {
                const status = resolveReservationStatus(reservation)
                const place = bundle.places?.find((candidate) => candidate.id === reservation.place_id)
                const placeName = place?.name || reservation.name || reservation.place_id
                const address = place?.address
                const mapHref = place?.google_maps_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place?.maps_query || placeName)}`
                const route = buildDayItemLink(bundle, reservation)
                const ics = buildReservationCalendarIcs(reservation)
                const icsHref = ics ? `data:text/calendar;charset=utf-8,${encodeURIComponent(ics)}` : null
                const summary = [reservation.name || '名稱未提供', formatDate(reservation.day), formatTime(reservation.time), placeName, address].filter(Boolean).join('｜')

                return (
                  <article className="reservation-card" key={reservation.id}>
                    <div className="reservation-time"><strong>{formatTime(reservation.time)}</strong><span>{formatDate(reservation.day)}</span></div>
                    <div className="reservation-main">
                      <div className="reservation-title-row"><div><span className={operationalStatusClass(status)}>{operationalStatusLabel(status)}</span><h2>{reservation.name || '預約名稱未提供'}</h2></div><span className="reservation-kind">{reservation.kind}</span></div>
                      <dl className="reservation-facts">
                        <div><dt>地點</dt><dd>{placeName}</dd></div>
                        <div><dt>地址</dt><dd>{address || '完整地址未提供'}</dd></div>
                        <div><dt>資料來源</dt><dd>{reservation.source || 'Canonical Trip'}</dd></div>
                        <div><dt>最後確認</dt><dd>{reservation.last_checked_at || '未提供'}</dd></div>
                      </dl>
                      {reservation.unresolved ? <p className="reservation-risk"><strong>待處理：</strong>此預約尚有未補齊欄位，請勿把目前內容視為最終確認。</p> : null}
                      <div className="reservation-actions">
                        <button type="button" onClick={() => copyText(reservation.id, summary)}>{copying === reservation.id ? '摘要已複製' : '複製預約摘要'}</button>
                        <a href={route}>回到當日行程</a>
                        <a href={mapHref} target="_blank" rel="noreferrer">地圖</a>
                        {icsHref ? <a href={icsHref} download={`${reservation.id}.ics`}>加入行事曆</a> : null}
                        {reservation.phone ? <a href={`tel:${reservation.phone}`}>撥打電話</a> : null}
                        {reservation.official_url ? <a className="primary" href={reservation.official_url} target="_blank" rel="noreferrer">官方連結</a> : null}
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          </section>
        ))}
      </div>

      {bundle.reservations.length === 0 ? <div className="honest-empty"><strong>Canonical Trip 尚無預約紀錄</strong><p>頁面不會從一般行程文字自行推定已預約。固定行程仍可在每日時間軸查看。</p><a href="#/today">查看每日行程</a></div> : null}
      <footer className="data-footnote">資料快照：{bundle.meta.generated_at}。場次與營業狀態請以官方最新通知為準。</footer>
    </section>
  )
}
