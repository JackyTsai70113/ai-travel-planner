import { useMemo } from 'react'
import { Bundle, buildMapsLink, findPlaceAddress, findPlaceLabel } from '../contracts/trip'
import { buildRoutePath } from '../app/route-registry'

interface LodgingPageProps {
  bundle: Bundle
}

interface LodgingItem {
  id: string
  placeId: string
  checkInDate: string
  checkOutDate?: string
  nights?: number
  route: string
}

export function LodgingPage({ bundle }: LodgingPageProps) {
  const lodgings = useMemo<LodgingItem[]>(() => {
    const lodgingsByPlace = bundle.selected.hotel_place_ids.map((placeId) => {
      const dayWithCheckIn = bundle.days.find((day) => day.items.some((item) => item.kind === 'check_in' && item.place_id === placeId))
      if (!dayWithCheckIn) return null

      const checkInItem = dayWithCheckIn.items.find(
        (item) => item.kind === 'check_in' && item.place_id === placeId && item.id && item.start_at,
      )
      if (!checkInItem) return null

      const checkOutItem = bundle.days
        .slice(bundle.days.indexOf(dayWithCheckIn))
        .flatMap((day) => day.items)
        .find((item) => item.kind === 'check_out' && item.place_id === placeId && item.start_at)

      const checkoutDate = checkOutItem?.start_at ? checkOutItem.start_at.slice(0, 10) : undefined
      const nights = checkoutDate
        ? Math.max(
          Math.round(
            (new Date(`${checkoutDate}T00:00:00+09:00`).getTime() - new Date(`${checkInItem.start_at?.slice(0, 10)}T00:00:00+09:00`).getTime()) /
              (1000 * 60 * 60 * 24),
          ),
          1,
        )
        : undefined

      return {
        id: `${placeId}-${checkInItem.id}`,
        placeId,
        checkInDate: checkInItem.start_at?.slice(0, 10) || '',
        checkOutDate: checkoutDate,
        nights,
        route: buildRoutePath({ section: 'today', day: checkInItem.start_at?.slice(0, 10), item: checkInItem.id }),
      }
    }).filter(Boolean) as LodgingItem[]

    return lodgingsByPlace.filter((item) => item.checkInDate)
  }, [bundle.days, bundle.selected.hotel_place_ids])

  return (
    <section className="card hub-card-wrapper" aria-label="住宿">
      <header className="hub-header">
        <h2>住宿</h2>
        <p>依據公共 itinerary 片段與目前已提供住宿主鍵，先呈現可核對欄位。</p>
      </header>

      <p className="shell-message">資料版本：{bundle.meta.generated_at}</p>

      <div className="hub-stats">
        <p>已列出住宿筆數：{lodgings.length}</p>
        <p>入住資料欄位可補齊程度：{lodgings.length ? '部分可確認' : '未提供完整欄位'}</p>
      </div>

      {lodgings.length > 0 ? (
        <div className="hub-section">
          {lodgings.map((lodging) => {
            const placeLabel = findPlaceLabel(bundle.places, lodging.placeId)
            const placeAddress = findPlaceAddress(bundle.places, lodging.placeId)
            return (
              <article className="hub-item" key={lodging.id}>
                <div className="hub-item-row">
                  <span className="hub-status confirmed">booked</span>
                  <h3>{placeLabel}</h3>
                </div>
                <p>入住日：{lodging.checkInDate || '待補'}</p>
                <p>退房日：{lodging.checkOutDate || '待補'}</p>
                <p>晚數：{lodging.nights ? `${lodging.nights} 晚` : '待補'}</p>
                {placeAddress ? <p>地址：{placeAddress}</p> : null}
                <p>已知設施：未提供（未在公共 read model 呈現）</p>
                <p>特殊需求：parking / luggage unloading / elevator / 廚房：待補</p>
                <div className="hub-actions">
                  <a className="hub-inline-button" href={buildMapsLink(placeLabel)} target="_blank" rel="noreferrer">
                    地圖
                  </a>
                  <a className="hub-inline-button" href={lodging.route}>
                    回行程（入住日）
                  </a>
                  <a className="hub-inline-button" href={`https://wa.me/?text=預約住宿：${encodeURIComponent(placeLabel)}`}>
                    一鍵複製提醒
                  </a>
                </div>
              </article>
            )
          })}
        </div>
      ) : (
        <p className="hub-empty">
          目前公開資料中僅有住宿 placeId 列表，未含入住/退房的完整時間欄位，將以「待補」呈現。
        </p>
      )}

      <p className="hub-footer">來源：{bundle.meta?.source_path || 'public-bundle'}，非即時更新。</p>
    </section>
  )
}
