import { useMemo, useState } from 'react'
import {
  Bundle,
  BundlePlace,
  buildMapsLink,
  operationalStatusClass,
  operationalStatusLabel,
} from '../contracts/trip'
import { buildRoutePath } from '../app/route-registry'

interface LodgingPageProps {
  bundle: Bundle
}
interface LodgingItem {
  id: string
  placeId: string
  place?: BundlePlace
  checkInDate?: string
  checkInTime?: string
  checkOutDate?: string
  checkOutTime?: string
  nights?: number
  boundaryNote: string
  route: string
  note?: string
}

function timeLabel(value: string | null | undefined) {
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '未提供'
}

function dateLabel(value: string | undefined) {
  if (!value) return '未提供'
  try {
    return new Intl.DateTimeFormat('zh-TW', {
      month: 'numeric',
      day: 'numeric',
      weekday: 'short',
      timeZone: 'Asia/Tokyo',
    }).format(new Date(`${value}T00:00:00+09:00`))
  } catch {
    return value
  }
}

function daysBetween(start?: string, end?: string) {
  if (!start || !end) return undefined
  const difference = new Date(`${end}T00:00:00+09:00`).getTime() - new Date(`${start}T00:00:00+09:00`).getTime()
  return Math.max(Math.round(difference / 86_400_000), 1)
}

export function LodgingPage({ bundle }: LodgingPageProps) {
  const [copiedId, setCopiedId] = useState('')
  const lodgings = useMemo<LodgingItem[]>(() => {
    const allItems = bundle.days.flatMap((day) => day.items)
    const base = bundle.selected.hotel_place_ids.map((placeId) => {
      const place = bundle.places?.find((candidate) => candidate.id === placeId)
      const checkIn = allItems.find((item) => item.kind === 'check_in' && item.place_id === placeId)
      const checkOut = allItems.find((item) => item.kind === 'check_out' && item.place_id === placeId)
      return { placeId, place, checkIn, checkOut }
    }).sort((a, b) => (a.checkIn?.start_at || '').localeCompare(b.checkIn?.start_at || ''))

    return base.map((entry, index) => {
      const checkInDate = entry.checkIn?.start_at?.slice(0, 10)
      const explicitCheckOut = entry.checkOut?.start_at?.slice(0, 10)
      const nextCheckIn = base[index + 1]?.checkIn?.start_at?.slice(0, 10)
      const checkOutDate = explicitCheckOut || nextCheckIn
      const boundaryNote = explicitCheckOut
        ? '退房時間已列入行程'
        : nextCheckIn
          ? '退房日依下一處入住日呈現；確切退房時間未提供'
          : '退房日與時間未提供'
      return {
        id: entry.placeId,
        placeId: entry.placeId,
        place: entry.place,
        checkInDate,
        checkInTime: entry.checkIn?.start_at || undefined,
        checkOutDate,
        checkOutTime: entry.checkOut?.start_at || undefined,
        nights: daysBetween(checkInDate, checkOutDate),
        boundaryNote,
        route: buildRoutePath({ section: 'today', day: checkInDate, item: entry.checkIn?.id }),
        note: entry.checkIn?.notes || undefined,
      }
    })
  }, [bundle.days, bundle.places, bundle.selected.hotel_place_ids])

  const totalNights = lodgings.reduce((sum, lodging) => sum + (lodging.nights || 0), 0)
  const copyAddress = async (lodging: LodgingItem) => {
    if (!lodging.place?.address) return
    try {
      await navigator.clipboard.writeText(`${lodging.place.name || lodging.placeId}\n${lodging.place.address}`)
      setCopiedId(lodging.id)
      window.setTimeout(() => setCopiedId(''), 1400)
    } catch {
      setCopiedId('error')
    }
  }

  return (
    <section className="lodging-workspace" aria-label="住宿手冊">
      <header className="page-intro">
        <div><p className="eyebrow">STAY GUIDE</p><h1>住宿接力</h1><p>入住日期、地址與當日行程放在一起；未提供的設備與需求不自行推論。</p></div>
        <div className="page-intro-stats"><span><strong>{lodgings.length}</strong> 處住宿</span><span><strong>{totalNights}</strong> 晚</span></div>
      </header>

      <div className="lodging-route-strip" aria-label="住宿順序">
        {lodgings.map((lodging, index) => <div key={lodging.id}><span>{index + 1}</span><strong>{lodging.place?.name || lodging.placeId}</strong><small>{dateLabel(lodging.checkInDate)}</small></div>)}
      </div>

      <div className="lodging-card-list">
        {lodgings.map((lodging, index) => {
          const status = lodging.checkInDate && lodging.place?.address ? 'confirmed' : 'unresolved'
          const mapsHref = lodging.place?.google_maps_url || buildMapsLink(lodging.place?.maps_query || lodging.place?.name || lodging.placeId)
          return (
            <article className="lodging-card" key={lodging.id}>
              <div className="lodging-card-number"><span>STAY</span><strong>{String(index + 1).padStart(2, '0')}</strong></div>
              <div className="lodging-card-main">
                <header>
                  <div><span className={operationalStatusClass(status)}>{operationalStatusLabel(status)}</span><h2>{lodging.place?.name || lodging.placeId}</h2>{lodging.place?.name_ja ? <p>{lodging.place.name_ja}</p> : null}</div>
                  <span className="night-pill">{lodging.nights ? `${lodging.nights} 晚` : '晚數未確認'}</span>
                </header>
                {lodging.place?.image_url ? <figure className="lodging-photo"><img src={lodging.place.image_url} alt={lodging.place.image_alt || `${lodging.place.name || lodging.placeId} 圖片`} loading="lazy" /><figcaption>{lodging.place.image_source_url ? <a href={lodging.place.image_source_url} target="_blank" rel="noreferrer">圖片來源</a> : '住宿圖片'}</figcaption></figure> : null}
                <div className="stay-dates">
                  <div><small>CHECK IN</small><strong>{dateLabel(lodging.checkInDate)}</strong><span>{timeLabel(lodging.checkInTime)}</span></div>
                  <i>→</i>
                  <div><small>CHECK OUT</small><strong>{dateLabel(lodging.checkOutDate)}</strong><span>{timeLabel(lodging.checkOutTime)}</span></div>
                </div>
                <div className="stay-address"><span aria-hidden="true">⌖</span><div><small>完整地址</small><p>{lodging.place?.address || 'Canonical Trip 尚未提供完整地址'}</p></div></div>
                {lodging.place?.opening_hours_note ? <p className="stay-note"><strong>入住／退房規則：</strong>{lodging.place.opening_hours_note}</p> : null}
                <p className="stay-boundary-note">{lodging.boundaryNote}</p>
                {lodging.note ? <p className="stay-note"><strong>入住提醒：</strong>{lodging.note}</p> : null}
                {lodging.place?.accessibility_notes ? <p className="stay-note"><strong>家庭／無障礙：</strong>{lodging.place.accessibility_notes}</p> : null}
                <div className="stay-actions">
                  <a className="primary" href={mapsHref} target="_blank" rel="noreferrer">開啟導航</a>
                  <button type="button" disabled={!lodging.place?.address} onClick={() => copyAddress(lodging)}>{copiedId === lodging.id ? '地址已複製' : '複製住宿地址'}</button>
                  <a href={lodging.route}>查看入住日</a>
                  {lodging.place?.official_url ? <a href={lodging.place.official_url} target="_blank" rel="noreferrer">官方網站</a> : null}
                </div>
              </div>
            </article>
          )
        })}
      </div>

      {lodgings.length === 0 ? <div className="honest-empty"><strong>尚無住宿主鍵</strong><p>Canonical Trip 目前未列出住宿，頁面不會自行猜測。</p></div> : null}
      <footer className="data-footnote">入住與退房以 Canonical Trip 已知時間為準。</footer>
    </section>
  )
}
