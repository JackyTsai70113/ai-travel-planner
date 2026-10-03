import { useMemo } from 'react'
import { Bundle, BundleDayItem, BundleProvenance, findPlaceLabel } from '../contracts/trip'
import { MapPinLink } from '../components/MapPinLink'
import { googleMapsHrefForPlace } from '../lib/google-maps-links'
import { usableOfficialHref } from '../lib/official-links'

interface FoodPageProps { bundle: Bundle }

function timeLabel(value: string | null): string {
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '時間待確認'
}

function Attribution({ values }: { values?: BundleProvenance[] | null }) {
  const entries = (values || []).filter((value) => value.provider || value.source_url || value.retrieved_at)
  if (!entries.length) return null
  return <small className="food-source">依據：{entries.map((entry, index) => <span key={`${entry.provider}-${entry.retrieved_at}-${index}`}>
    {index ? '、' : ''}{entry.provider || '公開紀錄'}{entry.retrieved_at ? `；查核時間 ${entry.retrieved_at}` : ''}{entry.source_url ? <>；<a href={entry.source_url} target="_blank" rel="noreferrer">查看</a></> : ''}
  </span>)}</small>
}

export function FoodPage({ bundle }: FoodPageProps) {
  const facts = useMemo(() => new Map((bundle.restaurant_facts || []).map((item) => [item.place_id, item.fields || {}])), [bundle.restaurant_facts])
  const groups = useMemo(() => bundle.days.map((day, index) => ({
    dayNumber: index + 1,
    date: day.date,
    meals: day.items.filter((item) => item.kind === 'meal' || item.kind === 'food'),
  })).filter((group) => group.meals.length > 0), [bundle.days])

  return <section className="food-workspace" aria-label="餐飲與補給">
    <header className="page-intro food-intro"><div><p className="eyebrow">每日餐飲</p><h1>吃什麼，一眼就知道</h1></div></header>
    {groups.length ? <div className="food-day-groups">{groups.map((group) => <section className="food-day" key={group.date}>
      <header><span>第 {group.dayNumber} 天</span><h2>{group.date}</h2></header>
      <div className="food-card-grid">{group.meals.map((meal: BundleDayItem) => {
        const place = bundle.places?.find((candidate) => candidate.id === meal.place_id)
        const name = findPlaceLabel(bundle.places, meal.place_id)
        const record = facts.get(meal.place_id)
        const mapHref = googleMapsHrefForPlace(place, name)
        const officialHref = usableOfficialHref(place?.official_url)
        const specialHours = record?.opening_hours?.special_hours?.find((hours) => hours.date === group.date)
        const regularIntervals = record?.opening_hours?.intervals || []
        const openingLabel = specialHours
          ? specialHours.status === 'closed' ? '當日休息'
            : specialHours.status === 'open' ? specialHours.intervals.map((interval) => `${interval.opens_at}–${interval.closes_at}`).join('、') || null
              : null
          : record?.opening_hours?.status === 'fresh' && regularIntervals.length
            ? `一般營業時間：${regularIntervals.map((interval) => `${['一','二','三','四','五','六','日'][interval.weekday]} ${interval.opens_at}–${interval.closes_at}`).join('、')}`
            : null
        const fieldProvenance = record?.field_provenance
        return <article className="food-card" key={meal.id}>
          {place?.image_url ? <figure className="food-photo"><img src={place.image_url} alt={place.image_alt || name} loading="lazy" />{place.image_source_url ? <figcaption><a href={place.image_source_url} target="_blank" rel="noreferrer">圖片來源</a></figcaption> : null}</figure> : null}
          <div className="food-card-time">{timeLabel(meal.start_at)}</div>
          <div className="food-place-heading"><h3>{officialHref ? <a className="official-title-link" href={officialHref} target="_blank" rel="noreferrer">{name}</a> : name}</h3><MapPinLink href={mapHref} label={`在 Google Maps 開啟 ${name}`} /></div>
          <dl>{meal.end_at ? <div><dt>預計時段</dt><dd>{timeLabel(meal.start_at)}–{timeLabel(meal.end_at)}</dd></div> : null}
            {record?.cuisine ? <div><dt>料理類型</dt><dd>{record.cuisine}<Attribution values={fieldProvenance?.cuisine} /></dd></div> : null}
            {record?.price_range ? <div><dt>價格參考</dt><dd>{record.price_range}<Attribution values={fieldProvenance?.price_range} /></dd></div> : null}
            {openingLabel ? <div><dt>營業時間</dt><dd>{openingLabel}<Attribution values={record?.opening_hours?.provenance ? [record.opening_hours.provenance] : fieldProvenance?.opening_hours} /></dd></div> : null}
            {record?.wait_risk && record.wait_risk !== 'unknown' ? <div><dt>等候風險</dt><dd>{record.wait_risk}<Attribution values={fieldProvenance?.wait_risk} /></dd></div> : null}
            {record?.reservation_required !== undefined ? <div><dt>訂位</dt><dd>{record.reservation_required ? record.reservation_url ? <a href={record.reservation_url} target="_blank" rel="noreferrer">需訂位，開啟預約資訊</a> : '需訂位' : '無需訂位'}<Attribution values={fieldProvenance?.reservation_required} /></dd></div> : null}
          </dl>
          {record?.recommended_dishes?.length ? <div className="food-picks"><strong>有來源的推薦餐點</strong><ol>{record.recommended_dishes.map((dish) => <li key={dish.name}><strong>{dish.name}</strong>{dish.note ? <span>{dish.note}</span> : null}<Attribution values={dish.provenance ? [dish.provenance] : []} /></li>)}</ol></div> : null}
          {record?.schedule?.alternatives?.length ? <div className="food-alternatives"><strong>同餐段候補</strong><ul>{record.schedule.alternatives.map((alternative) => {
            const alternate = bundle.places?.find((candidate) => candidate.id === alternative.place_id)
            const alternateName = findPlaceLabel(bundle.places, alternative.place_id)
            const alternateFacts = facts.get(alternative.place_id)
            return <li key={`${alternative.day}-${alternative.meal_period}-${alternative.place_id}`}>
              <a href={googleMapsHrefForPlace(alternate, alternateName)} target="_blank" rel="noreferrer">{alternateName}</a>
              {alternateFacts?.price_range ? <span>；{alternateFacts.price_range}</span> : null}
              <span>；營業時間已查核，行程會再依當日實際順序確認可達性</span>
            </li>
          })}</ul></div> : null}
        </article>
      })}</div>
    </section>)}</div> : <p className="food-empty">目前沒有營業時間、路線均已驗證的餐廳安排；餐飲仍待選擇，未以夜市區域或景點資料代替店家。</p>}
  </section>
}
