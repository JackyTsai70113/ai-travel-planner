import { useMemo, useState } from 'react'
import {
  Bundle,
  BundleReservation,
  buildMapsLink,
  operationalStatusClass,
  operationalStatusLabel,
} from '../contracts/trip'
import { findPlaceAddress, findPlaceLabel } from '../contracts/trip'
import { buildRoutePath } from '../app/route-registry'

interface ReservationsPageProps {
  bundle: Bundle
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

function formatTime(value: string | null) {
  if (!value) return '待補'
  return new Intl.DateTimeFormat('zh-TW', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function resolveReservationStatus(reservation: BundleReservation, isUnresolved: boolean) {
  if (isUnresolved || reservation.unresolved) return 'unresolved' as const
  if (reservation.status) return reservation.status
  if (reservation.time && reservation.name) return 'confirmed'
  if (reservation.time || reservation.name) return 'estimated'
  return 'unverified'
}

function buildDayItemLink(bundle: Bundle, reservation: BundleReservation) {
  const day = bundle.days.find((itemDay) => itemDay.date === reservation.day) ?? bundle.days[0]
  if (!day) return buildRoutePath({ section: 'today' })
  const direct = day.items.find((item) => item.id === reservation.id)
  if (direct) return buildRoutePath({ section: 'today', day: day.date, item: direct.id })

  const fallback = day.items.find((item) =>
    item.place_id === reservation.place_id &&
    reservation.time &&
    item.start_at &&
    item.start_at.slice(0, 16) === reservation.time.slice(0, 16),
  )
  if (fallback) return buildRoutePath({ section: 'today', day: day.date, item: fallback.id })
  return buildRoutePath({ section: 'today', day: day.date })
}

function buildReservationCalendarIcs(reservation: BundleReservation) {
  if (!reservation.time || !reservation.name) return null
  const parse = (value: string): Date => new Date(value)
  const startDate = parse(reservation.time)
  const start = `${startDate.getFullYear()}${String(startDate.getMonth() + 1).padStart(2, '0')}${String(startDate.getDate()).padStart(2, '0')}T${String(startDate.getHours()).padStart(2, '0')}${String(startDate.getMinutes()).padStart(2, '0')}00`
  const endDate = new Date(startDate.getTime() + 60 * 60 * 1000)
  const end = `${endDate.getFullYear()}${String(endDate.getMonth() + 1).padStart(2, '0')}${String(endDate.getDate()).padStart(2, '0')}T${String(endDate.getHours()).padStart(2, '0')}${String(endDate.getMinutes()).padStart(2, '0')}00`
  const title = reservation.name.replace(/\n/g, ' ')
  return `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Golden Trip//Operational Hub//EN
BEGIN:VEVENT
UID:${reservation.id}
DTSTART:${start}
DTEND:${end}
SUMMARY:${title}
DESCRIPTION:${reservation.kind}
END:VEVENT
END:VCALENDAR`
}

export function ReservationsPage({ bundle }: ReservationsPageProps) {
  const [copying, setCopying] = useState('')

  const grouped = useMemo(() => {
    const byDay = new Map<string, BundleReservation[]>()
    bundle.days.forEach((day) => {
      byDay.set(day.date, [])
    })

    bundle.reservations.forEach((reservation) => {
      const day = byDay.has(reservation.day) ? reservation.day : bundle.days[0]?.date || reservation.day
      if (!day) return
      byDay.set(day, [...(byDay.get(day) || []), reservation])
    })

    return [...byDay.entries()].map(([day, reservations]) => ({
      day,
      reservations: reservations.sort((a, b) => (a.time || '').localeCompare(b.time || '')),
    }))
  }, [bundle.days, bundle.reservations])

  const unresolvedCount = bundle.reservations.filter((reservation) => reservation.unresolved).length
  const estimatedCount = bundle.reservations.length - unresolvedCount

  const copyText = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopying(key)
      setTimeout(() => setCopying((current) => (current === key ? '' : current)), 1500)
    } catch {
      setCopying(`${key}-err`)
      setTimeout(() => setCopying((current) => (current === `${key}-err` ? '' : current)), 1200)
    }
  }

  return (
    <section className="card hub-card-wrapper" aria-label="預約與票券">
      <header className="hub-header">
        <h2>預約與票券</h2>
        <p>基於公共資料的目前可確認欄位，未填欄位不進行推論。</p>
      </header>

      {bundle.reservations.length ? (
        <>
          <div className="hub-stats">
            <p>總件數：{bundle.reservations.length}</p>
            <p>未補齊：{unresolvedCount}</p>
            <p>待驗證：{estimatedCount}</p>
          </div>

          <div className="shell-message">
            資料版本：{bundle.meta.generated_at}
          </div>

          {unresolvedCount > 0 ? (
            <p className="hub-alert">
              有尚未補齊關鍵欄位（時間、場景、地址、聯絡資訊）的預約，將保留「未補齊」狀態。
            </p>
          ) : null}

          {grouped.map((group) => (
            <section key={group.day} className="hub-section">
              <h3>{formatDate(group.day)}</h3>
              {group.reservations.length === 0 ? <p className="hub-empty">此日無預約。</p> : null}
              <ul className="hub-items">
                {group.reservations.map((reservation) => {
                  const status = resolveReservationStatus(reservation, reservation.unresolved || false)
                  const place = findPlaceLabel(bundle.places, reservation.place_id)
                  const address = findPlaceAddress(bundle.places, reservation.place_id)
                  const route = buildDayItemLink(bundle, reservation)
                  const ics = buildReservationCalendarIcs(reservation)
                  const icsHref = ics ? `data:text/calendar;charset=utf-8,${encodeURIComponent(ics)}` : null
                  const source = reservation.source || 'public-bundle'
                  const freshness = reservation.freshness || '未知'

                  return (
                    <li key={reservation.id} className="hub-item">
                      <div className="hub-item-row">
                        <span className={operationalStatusClass(status)}>{operationalStatusLabel(status)}</span>
                        <h4>{reservation.name || '未提供名稱'}</h4>
                      </div>
                      <p>時間：{formatTime(reservation.time)} / 場次：{reservation.kind}</p>
                      <p>地點：{place}</p>
                      <p>來源：{source} / 更新：{reservation.last_checked_at || '未提供'} / Freshness：{freshness}</p>
                      {address ? <p>地址：{address}</p> : null}

                      <div className="hub-actions">
                        <button
                          type="button"
                          onClick={() =>
                            copyText(`summary-${reservation.id}`, `${reservation.name || '預約'}｜${place}｜${reservation.time || '時間待補'}`)}
                        >
                          {copying === `summary-${reservation.id}` ? '已複製' : '複製摘要'}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            copyText(
                              `jp-${reservation.id}`,
                              `${reservation.name || 'ご予約'}：${reservation.day || ''} ${place}。最終確認お願いします。`,
                            )
                          }
                        >
                          {copying === `jp-${reservation.id}` ? '已複製' : '複製日文摘要'}
                        </button>
                        <a className="hub-inline-button" href={route}>
                          回行程
                        </a>
                        <a className="hub-inline-button" href={buildMapsLink(place)} target="_blank" rel="noreferrer">
                          導航
                        </a>
                        {icsHref ? (
                          <a className="hub-inline-button" href={icsHref} download={`${reservation.id}.ics`}>
                            加入行事曆
                          </a>
                        ) : null}
                        {reservation.phone ? <a href={`tel:${reservation.phone}`}>{reservation.phone}</a> : null}
                        {reservation.official_url ? (
                          <a href={reservation.official_url} target="_blank" rel="noreferrer">
                            官方連結
                          </a>
                        ) : null}
                      </div>

                      {reservation.official_url || reservation.phone ? (
                        <p className="hub-meta">網路行動與電話依使用者環境執行，請留意網路可用性。</p>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </>
      ) : (
        <p className="hub-empty">目前沒有可展示的預約項目。</p>
      )}
    </section>
  )
}
