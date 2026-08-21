import {
  Bundle,
  findPlaceLabel,
  formatMoney,
  toFriendlyStatus,
} from '../contracts/trip'
import type { TripCatalogEntry } from '../contracts/trip-registry'

interface OverviewPageProps {
  bundle: Bundle | null
  trip: TripCatalogEntry | null
}

function resolveStatusBadge(readiness: TripCatalogEntry['readiness']): { className: string; text: string } {
  if (readiness === 'ready') return { className: 'status-pill status-ready', text: '可安心出發（仍需確認最新條件）' }
  if (readiness === 'incomplete') return { className: 'status-pill status-incomplete', text: '資料待補，尚未完全確認' }
  return { className: 'status-pill status-blocked', text: '關鍵阻斷，建議補齊資料後再出發' }
}

function resolvePublicationBadge(status: TripCatalogEntry['status']): { className: string; text: string } {
  if (status === 'published') return { className: 'status-pill status-published', text: '已發布' }
  if (status === 'preview') return { className: 'status-pill status-preview', text: '預覽版本' }
  return { className: 'status-pill status-archived', text: '封存版本' }
}

function resolveHeroImage(trip: TripCatalogEntry | null): string {
  if (!trip) return 'linear-gradient(130deg, #0f172a, #173c61)'
  if (trip.cover_media.kind === 'image' && trip.cover_media.url) {
    return `linear-gradient(120deg, rgba(8, 16, 28, 0.45), rgba(8, 16, 28, 0.2)), url(${trip.cover_media.url}) center/cover no-repeat`
  }
  return trip.cover_media.gradient || 'linear-gradient(130deg, #0f172a, #173c61)'
}

function resolveCriticalCount(bundle: Bundle | null, trip: TripCatalogEntry | null): number {
  if (!bundle) return trip ? trip.critical_alert_count : 0
  const unresolvedReservations = bundle.reservations.filter((item) => item.unresolved).length
  return bundle.validation.filter((item) => item.severity === 'error' || item.severity === 'warning').length + unresolvedReservations
}

function toDateText(value: string): string {
  if (!value) return '--'
  return value
}

export function OverviewPage({ bundle, trip }: OverviewPageProps) {
  const publication = resolvePublicationBadge(trip?.status || 'preview')
  const readiness = resolveStatusBadge(trip?.readiness || 'incomplete')
  const heroImage = resolveHeroImage(trip)
  const criticalCount = resolveCriticalCount(bundle, trip || null)

  const fallbackHeroNote = trip ? trip.hero_summary : '行程資料待載入，仍可先閱讀公開摘要。'
  const destinationText = trip ? trip.destination_regions.join(' / ') : '日本'
  const dateText = trip
    ? `${trip.date_range.start_date} ~ ${trip.date_range.end_date}（${trip.duration_days} 天）`
    : '資料載入中'
  const travelersText = trip ? trip.travelers_summary : '--'

  if (!bundle) {
    return (
      <section className="trip-overview-shell">
        <article className="trip-overview-hero" style={{ background: heroImage }}>
          <p className="trip-hero-eyebrow">AI Travel Planner</p>
          <h1>{trip?.title || 'Trip Landing'}</h1>
          <p className="muted">{destinationText}</p>
          <p>{dateText}</p>
          <p>{travelersText}</p>
          <div className="hero-tags">
            <span className={publication.className}>{publication.text}</span>
            <span className={readiness.className}>{readiness.text}</span>
            <span className="status-pill status-warning">提醒 {criticalCount} 則</span>
          </div>
          <p className="hero-summary">{fallbackHeroNote}</p>
          <div className="hero-actions">
            <a href="#/today">查看今日行程</a>
            <a href="#/map">地圖</a>
            <a href="#/reservation">預約</a>
            <a href="#/sources">資料來源</a>
          </div>
        </article>
        <section className="card-shell">
          <h2>資料載入中</h2>
          <p className="muted">行程資料尚在載入，稍後會顯示每日主題、住宿與預約細節。</p>
        </section>
      </section>
    )
  }

  const unresolvedReservations = bundle.reservations.filter((item) => item.unresolved).slice(0, 3)
  const firstDays = bundle.days.slice(0, 3)

  return (
    <section className="trip-overview-shell">
      <article className="trip-overview-hero" style={{ background: heroImage }}>
        <p className="trip-hero-eyebrow">AI Travel Planner</p>
        <h1>{trip?.title || bundle.title}</h1>
        <p className="muted">{destinationText}</p>
        <p>{dateText}</p>
        <p>{travelersText}</p>
        <div className="hero-tags">
          <span className={publication.className}>{publication.text}</span>
          <span className={readiness.className}>{readiness.text}</span>
          <span className="status-pill status-warning">提醒 {criticalCount} 則</span>
        </div>
        <p className="hero-summary">{trip?.hero_summary || fallbackHeroNote}</p>
        <p className="muted">最後更新：{trip?.last_generated || '--'}｜確認：{trip?.last_verified || '--'}</p>
        <div className="hero-actions">
          <a href="#/today">查看今日行程</a>
          <a href="#/map">地圖</a>
          <a href="#/reservation">預約</a>
          <a href="#/sources">資料來源</a>
        </div>
      </article>

      <section className="card-shell">
        <h2>行程摘要</h2>
        <p>行程狀態：{toFriendlyStatus(bundle.status)} | 資料更新：{bundle.meta.generated_at}</p>
        <p>航班/轉運：{bundle.selected.flight_ids.join('、') || '待補'}</p>
        <p>住宿：{bundle.selected.hotel_place_ids.join('、') || '待補'}</p>
        <p>資料快照總預算：{formatMoney(bundle.budget?.total)}</p>
      </section>

      <section className="card-shell">
        <h2>每日主題（預覽）</h2>
        <div className="daily-theme-grid">
          {firstDays.map((day) => (
            <article key={day.date} className="daily-theme-item">
              <p className="muted">{toDateText(day.date)}</p>
              <h3>{day.summary}</h3>
              {day.items.length === 0 ? <p className="muted">尚未設定明細</p> : null}
              {day.items.slice(0, 3).map((item) => (
                <p key={`${day.date}-${item.id}`} className="muted">
                  {item.kind} ｜ {item.kind === 'stay' ? '住宿' : item.kind}
                </p>
              ))}
            </article>
          ))}
          {firstDays.length === 0 ? <p className="muted">未提供每日主題</p> : null}
        </div>
      </section>

      <section className="card-shell">
        <h2>預約提醒</h2>
        {unresolvedReservations.length === 0 ? <p className="muted">目前沒有未解決的關鍵預約警示。</p> : null}
        <ul>
          {unresolvedReservations.map((item) => (
            <li key={item.id}>
              <strong>{item.kind}</strong>：{findPlaceLabel(bundle.places || [], item.place_id)}
              {' '}
              <span className="muted">（{item.day} {item.time || '時間待補'}）</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card-shell">
        <h2>關鍵提醒</h2>
        <ul>
          {bundle.validation.map((item) => (
            <li key={item.code}>
              <strong>{item.severity}</strong>：{item.message}
            </li>
          ))}
        </ul>
      </section>
    </section>
  )
}
