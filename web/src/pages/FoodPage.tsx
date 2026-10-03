import { useMemo } from 'react'
import { Bundle, BundleDayItem, BundleProvenance, findPlaceLabel } from '../contracts/trip'
import { MapPinLink } from '../components/MapPinLink'
import { googleMapsHrefForPlace } from '../lib/google-maps-links'
import { usableOfficialHref } from '../lib/official-links'

interface FoodPageProps { bundle: Bundle }
const mealPeriods = [
  { key: 'breakfast', label: '早餐' },
  { key: 'lunch', label: '午餐' },
  { key: 'dinner', label: '晚餐' },
] as const

function mealPeriodFor(placeId: string, dayNumber: number, startAt: string | null, facts: Map<string, NonNullable<Bundle['restaurant_facts']>[number]['fields']>) {
  const explicit = facts.get(placeId)?.schedule
  if (explicit?.day === dayNumber && explicit.meal_period) return explicit.meal_period
  if (!startAt) return null
  const hour = Number(startAt.match(/T(\d{2}):/)?.[1])
  if (!Number.isFinite(hour)) return null
  return hour < 11 ? 'breakfast' : hour < 16 ? 'lunch' : 'dinner'
}

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
  })), [bundle.days])

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
        const intervalLabel = (interval: { opens_at: string; closes_at: string; last_order_at?: string; last_order_day_offset?: number }) => `${interval.opens_at}–${interval.closes_at}${interval.last_order_at ? `（最後點餐 ${interval.last_order_day_offset ? '次日 ' : ''}${interval.last_order_at}）` : ''}`
        const openingLabel = specialHours
          ? specialHours.status === 'closed' ? '當日休息'
            : specialHours.status === 'open' ? specialHours.intervals.map(intervalLabel).join('、') || null
              : null
          : record?.opening_hours?.status === 'fresh' && regularIntervals.length
            ? `一般營業時間：${regularIntervals.map((interval) => `${['一','二','三','四','五','六','日'][interval.weekday]} ${intervalLabel(interval)}`).join('、')}`
            : null
        const fieldProvenance = record?.field_provenance
        return <article className="food-card" key={meal.id}>
          {place?.image_url ? <figure className="food-photo"><img src={place.image_url} alt={place.image_alt || name} loading="lazy" />{place.image_source_url ? <figcaption><a href={place.image_source_url} target="_blank" rel="noreferrer">圖片來源</a></figcaption> : null}</figure> : null}
          <div className="food-card-time">{timeLabel(meal.start_at)}</div>
          <div className="food-place-heading"><h3>{officialHref ? <a className="official-title-link" href={officialHref} target="_blank" rel="noreferrer">{name}</a> : name}</h3><MapPinLink href={mapHref} label={`在 Google Maps 開啟 ${name}`} /></div>
          <dl>{meal.end_at ? <div><dt>預計時段</dt><dd>{timeLabel(meal.start_at)}–{timeLabel(meal.end_at)}</dd></div> : null}
            {record?.schedule?.selection_reason ? <div><dt>選擇原因</dt><dd>{record.schedule.selection_reason}</dd></div> : null}
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
              {alternateFacts?.price_range ? <span>；{alternateFacts.price_range}<Attribution values={alternateFacts.field_provenance?.price_range} /></span> : null}
              <span>；營業時間已查核，行程會再依當日實際順序確認可達性</span>
              <Attribution values={alternateFacts?.opening_hours?.provenance ? [alternateFacts.opening_hours.provenance] : alternateFacts?.field_provenance?.opening_hours} />
            </li>
          })}</ul></div> : null}
        </article>
      })}</div>
      <div className="food-meal-gaps" aria-label="尚未安排的餐段"><strong>{group.meals.length ? '尚未安排的餐段' : '餐飲仍待選擇'}</strong><ul>{mealPeriods.filter((period) => !group.meals.some((meal) => mealPeriodFor(meal.place_id, group.dayNumber, meal.start_at, facts) === period.key)).map((period) => <li key={period.key}>{period.label}：尚待選擇或確認不安排</li>)}</ul></div>
    </section>)}</div> : <p className="food-empty">目前沒有行程日期可顯示餐段狀態。</p>}
  </section>
}
