import { useState } from 'react'

import type {
  PublicTripBundle,
  TripCatalogEntry,
  TripReadiness,
  TripPublicationStatus,
} from '../../contracts/trip-registry'

type SwUiStatus = 'unknown' | 'registering' | 'ready' | 'failed' | 'unsupported'
export type RouteSetter = (next: { route: 'home' | 'trip'; slug?: string }) => void

interface TripLandingOverviewProps {
  trip: TripCatalogEntry | null
  bundle: PublicTripBundle | null
  error: string
  setRoute: RouteSetter
  swStatus: { status: SwUiStatus; message: string }
}

function resolveBadgeClass(readiness: TripReadiness): string {
  if (readiness === 'ready') return 'status-pill status-ready'
  if (readiness === 'incomplete') return 'status-pill status-incomplete'
  return 'status-pill status-blocked'
}

function resolveReadinessText(readiness: TripReadiness): string {
  if (readiness === 'ready') return '可安心出發（仍需檢核行程細節）'
  if (readiness === 'incomplete') return '資料待補，尚非最終確認'
  return '關鍵阻斷，請補齊關聯資料'
}

function resolveStatusClass(status: TripPublicationStatus): string {
  if (status === 'published') return 'status-pill status-published'
  if (status === 'preview') return 'status-pill status-preview'
  return 'status-pill status-archived'
}

function resolveStatusText(status: TripPublicationStatus): string {
  if (status === 'published') return '已發布'
  if (status === 'preview') return '預覽'
  return '封存'
}

function criticalCount(bundle: PublicTripBundle | null): number {
  if (!bundle) return 0
  return bundle.validation.filter((item) => item.severity === 'error' || item.severity === 'warning').length +
    bundle.reservations.filter((item) => item.unresolved).length
}

export default function TripLandingOverview({ trip, bundle, error, setRoute, swStatus }: TripLandingOverviewProps) {
  const [imageFailed, setImageFailed] = useState(false)

  if (!trip) {
    return (
      <div className="trip-overview-shell card-shell">
        <p className="meta-error">找不到該行程</p>
        <button type="button" onClick={() => setRoute({ route: 'home' })}>回首頁</button>
      </div>
    )
  }

  const tripSummary = trip.hero_summary || '目前無摘要資料。'
  const coverFallback = trip.cover_media.gradient || 'linear-gradient(130deg, #0f172a, #1d4ed8)'
  const showImageMedia = trip.cover_media.kind === 'image' && !!trip.cover_media.url
  const bgStyle = showImageMedia && !imageFailed && trip.cover_media.url
    ? `linear-gradient(120deg, rgba(8, 16, 32, 0.65), rgba(8, 16, 32, 0.5)), url(${trip.cover_media.url}) center/cover no-repeat`
    : coverFallback

  return (
    <article className="trip-overview-shell">
      {showImageMedia && trip.cover_media.url && (
        <img
          src={trip.cover_media.url}
          alt={trip.cover_media.alt || trip.title}
          onError={() => setImageFailed(true)}
          style={{ display: 'none' }}
        />
      )}
      <section className="trip-overview-hero" style={{ background: bgStyle }}>
        <div>
          <button type="button" onClick={() => setRoute({ route: 'home' })}>返回 catalog</button>
          <p className="trip-hero-eyebrow">AI Travel Planner</p>
          <h1>{trip.title}</h1>
          <p>{trip.destination_regions.join(' / ')}</p>
          <p>{trip.date_range.start_date} ~ {trip.date_range.end_date}（{trip.duration_days} 天）</p>
          <p>{trip.travelers_summary}</p>
          <div className="hero-tags">
            <span className={resolveStatusClass(trip.status)}>{resolveStatusText(trip.status)}</span>
            <span className={resolveBadgeClass(trip.readiness)}>{resolveReadinessText(trip.readiness)}</span>
            <span className="status-pill">提醒 {trip.critical_alert_count + criticalCount(bundle)} 則</span>
          </div>
          <p className="hero-summary">{tripSummary}</p>
          {trip.key_messages.map((message) => <p key={message} className="muted">• {message}</p>)}
          {imageFailed && trip.cover_media.fallback && <p className="muted">封面預覽失敗，已改用備援視覺。</p>}
        </div>
      </section>

      <section className="card-shell">
        <h2>首屏快速動作</h2>
        <div className="actions-row">
          <a href="#itinerary">查看今日行程</a>
          <a href="#full-itinerary">完整行程</a>
          <a href="#map">地圖</a>
          <a href="#booking">自駕</a>
          <a href="#booking">固定預約</a>
        </div>
        <p className="muted">最後更新：{trip.last_generated} / 最近驗證：{trip.last_verified}</p>
        <p>離線與安裝：{swStatus.status === 'ready' ? '快取可用，離線可讀取核心頁面' : swStatus.message || '未完成離線註冊'}</p>
      </section>

      <section className="card-shell" id="full-itinerary">
        <h2>行程摘要</h2>
        {error && <p className="meta-error">資料讀取失敗：{error}</p>}
        {!bundle && !error && <p className="muted">資料載入中…</p>}
        {bundle && (
          <>
            <h3>每日主題</h3>
            <ul>
              {bundle.days.slice(0, 3).map((day) => (
                <li key={day.date}>{day.date}：{day.summary}</li>
              ))}
            </ul>

            <h3>飛行 / 交通</h3>
            <p>{bundle.selected.flight_ids.length ? bundle.selected.flight_ids.join('，') : '無固定航班快照'}</p>

            <h3>住宿</h3>
            <p>{bundle.selected.hotel_place_ids.length ? bundle.selected.hotel_place_ids.join('，') : '住宿未完整綁定'}</p>
          </>
        )}
      </section>

      <section className="card-shell" id="itinerary">
        <h2>關鍵提醒</h2>
        {bundle ? (
          <ul>
            {bundle.validation.map((item) => (
              <li key={item.code}>
                <strong>{item.severity}</strong>：{item.message}
              </li>
            ))}
            {bundle.reservations.filter((item) => item.unresolved).map((item) => (
              <li key={item.id}>固定預約待確認：{item.day} {item.time || ''} {item.name || ''}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">尚未載入提醒項目</p>
        )}
      </section>

      <section className="card-shell">
        <h2>原始資料時間與可信度</h2>
        {bundle && (
          <ul>
            <li>來源快照：{bundle.meta.generated_at || '--'}</li>
            <li>最後核對：{bundle.meta.source_path || '--'}</li>
            <li>下次重檢：{bundle.meta.next_recheck_at || '--'}</li>
          </ul>
        )}
      </section>
    </article>
  )
}
