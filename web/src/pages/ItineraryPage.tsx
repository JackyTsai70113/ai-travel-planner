import { useState } from 'react'
import { Bundle, buildMapsLink, findPlaceAddress, findPlaceLabel } from '../contracts/trip'
import { buildRoutePath, TripRoute } from '../app/route-registry'

interface ItineraryPageProps {
  bundle: Bundle
  route: TripRoute
  onNavigate: (next: Partial<TripRoute>) => void
}

export function ItineraryPage({ bundle, route, onNavigate }: ItineraryPageProps) {
  const [copiedId, setCopiedId] = useState('')
  const selectedDay =
    bundle.days.find((day) => day.date === route.day) ??
    (route.day ? (() => {
      const dayIndex = Number(route.day)
      if (!Number.isInteger(dayIndex) || dayIndex < 1) return undefined
      return bundle.days[dayIndex - 1]
    })() : undefined) ??
    bundle.days[0]

  const itemId = route.item

  if (!selectedDay) {
    return <section className="card">沒有可顯示的行程日。</section>
  }

  const copyText = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(label)
      setTimeout(() => setCopiedId((current) => (current === label ? '' : current)), 1200)
    } catch {
      setCopiedId('error')
      setTimeout(() => setCopiedId(''), 1200)
    }
  }

  return (
    <section className="card" aria-label="每日行程">
      <h2>每日行程</h2>
      <div className="day-tabs" role="tablist" aria-label="行程日程頁籤">
        {bundle.days.map((day, index) => (
          <button
            key={day.date}
            className={`day-tab ${day.date === selectedDay.date ? 'active' : ''}`}
            role="tab"
            aria-selected={day.date === selectedDay.date}
            onClick={() => onNavigate({ section: 'today', day: day.date })}
            type="button"
          >
            Day {index + 1}
            <span>{day.date}</span>
          </button>
        ))}
      </div>

      <div className="day">
        <h3>{selectedDay.date}</h3>
        <p>{selectedDay.summary}</p>
        <p className="muted">
          可直接複製連結：{buildRoutePath({ section: 'today', day: selectedDay.date })} /{' '}
          {buildRoutePath({ section: 'today', day: selectedDay.date, item: selectedDay.items[0]?.id })}
        </p>
        <ul>
          {selectedDay.items.map((item) => (
            <li className={`journey-item ${item.id === itemId ? 'item-highlight' : ''}`} key={item.id}>
              <div>
                <strong>{item.kind}</strong>
                <span>
                  {' '}
                  · {item.start_at ?? '—'} ~ {item.end_at ?? '—'}
                </span>
              </div>
              <div className="journey-meta">
                <span>地點: {findPlaceLabel(bundle.places, item.place_id)}</span>
                {findPlaceAddress(bundle.places, item.place_id) ? (
                  <span>地址: {findPlaceAddress(bundle.places, item.place_id)}</span>
                ) : null}
                {item.notes ? <span>備註: {item.notes}</span> : null}
                <a href={buildMapsLink(findPlaceLabel(bundle.places, item.place_id))} target="_blank" rel="noreferrer">
                  開啟 Google Maps
                </a>
                <a href={buildRoutePath({ section: 'today', day: selectedDay.date, item: item.id })}>複製路徑</a>
                <button
                  type="button"
                  onClick={() => copyText(`${selectedDay.date}-${item.id}`, findPlaceLabel(bundle.places, item.place_id))}
                >
                  {copiedId === `${selectedDay.date}-${item.id}` ? '已複製' : '複製地點'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
