import { useEffect, useState } from 'react'
import type { Bundle } from '../../contracts/trip'
import type { TripCatalogEntry } from '../../contracts/trip-registry'

type RouteSetter = (next: { route: 'home' | 'trip'; slug?: string }) => void

interface TripLandingOverviewProps {
  trip: TripCatalogEntry | null
  bundle: Bundle | null
  error: string
  setRoute: RouteSetter
}

function resolveStatusBadge(readiness: TripCatalogEntry['readiness']): { className: string; text: string } {
  if (readiness === 'ready') return { className: 'status-pill status-ready', text: '可安心出發（仍需檢核）' }
  if (readiness === 'incomplete') return { className: 'status-pill status-incomplete', text: '資料待補，尚非最終確認' }
  return { className: 'status-pill status-blocked', text: '關鍵阻斷，請補齊後再出發' }
}

function resolvePublicationBadge(status: TripCatalogEntry['status']): { className: string; text: string } {
  if (status === 'published') return { className: 'status-pill status-published', text: '已發布' }
  if (status === 'preview') return { className: 'status-pill status-preview', text: '預覽' }
  return { className: 'status-pill status-archived', text: '封存' }
}

function resolveCriticalAlertCount(bundle: Bundle | null, trip: TripCatalogEntry | null): number {
  if (!bundle) return trip ? trip.critical_alert_count : 0
  const unresolvedReservations = bundle.reservations.filter((item) => item.unresolved).length
  return bundle.validation.filter((item) => item.severity === 'error' || item.severity === 'warning').length + unresolvedReservations
}

export default function TripLandingOverview({ trip, bundle, error, setRoute }: TripLandingOverviewProps) {
  const [imageFailed, setImageFailed] = useState(false)
  const publication = resolvePublicationBadge(trip?.status || 'preview')
  const readiness = resolveStatusBadge(trip?.readiness || 'incomplete')
  const criticalCount = resolveCriticalAlertCount(bundle, trip || null)

  useEffect(() => {
    setImageFailed(false)
  }, [trip?.slug])

  const sectionDate = trip
    ? `${trip.date_range.start_date} ~ ${trip.date_range.end_date}（${trip.duration_days} 天）`
    : '--'
  const travelers = trip ? trip.travelers_summary : '--'
  const mediaFallback = trip?.cover_media.gradient || 'linear-gradient(130deg, #0f172a, #1f4d7f)'
  const hasImage = trip?.cover_media.kind === 'image' && !!trip.cover_media.url && !imageFailed
  const bgStyle = hasImage ? `linear-gradient(120deg, rgba(5, 13, 23, 0.62), rgba(5, 13, 23, 0.42)), url(${trip?.cover_media.url}) center/cover no-repeat` : mediaFallback

  return (
    <article className="trip-overview-shell">
      <section className="trip-overview-hero" style={{ background: bgStyle }}>
        <div>
          <button type="button" onClick={() => setRoute({ route: 'home' })}>返回 catalog</button>
          <p className="trip-hero-eyebrow">AI Travel Planner</p>
          <h1>{trip?.title || '未載入 Trip'}</h1>
          <p className="muted">{trip?.destination_regions.join(' / ') || '行程目的地未載入'}</p>
          <p>{sectionDate} / {travelers}</p>
          <div className="hero-tags">
            <span className={publication.className}>{publication.text}</span>
            <span className={readiness.className}>{readiness.text}</span>
            <span className="status-pill status-warning">提醒 {criticalCount} 則</span>
          </div>
          {trip?.hero_summary ? <p className="hero-summary">{trip.hero_summary}</p> : null}
          {trip?.key_messages?.map((message) => <p className="muted" key={message}>• {message}</p>)}
          {hasImage ? (
            <img
              src={trip?.cover_media.url}
              alt={trip?.cover_media.alt || trip?.title || 'trip cover'}
              onError={() => setImageFailed(true)}
              style={{ display: 'none' }}
            />
          ) : null}
          {imageFailed ? <p className="muted">封面載入失敗，已改用備援視覺</p> : null}
          <div className="hero-actions">
            <a href="#/today">查看今日行程</a>
            <a href="#/">開啟完整行程</a>
            <a href="#/map">地圖</a>
            <a href="#/reservation">預約</a>
          </div>
        </div>
      </section>

      {error ? <p className="meta-error">資料載入失敗：{error}</p> : null}

      <section className="card-shell">
        <h2>行程快照資訊</h2>
        <p>資料快照：{bundle?.meta.generated_at || trip?.last_generated || '--'}</p>
        <p>資料確認：{trip?.last_verified || '--'}</p>
        <p>資料來源：public-bundle 與公開 registry</p>
        {bundle ? (
          <p>最後驗證：{bundle.validation?.[0]?.message ? '已產生 validation 報告' : '無關鍵驗證問題'}</p>
        ) : <p>資料載入中...</p>}
      </section>

      <section className="card-shell">
        <h2>關鍵提醒</h2>
        {bundle ? (
          <ul>
            {bundle.validation.map((item) => (
              <li key={item.code}>
                <strong>{item.severity}</strong>：{item.message}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">等待行程資料載入</p>
        )}
      </section>
    </article>
  )
}
