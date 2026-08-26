import { useMemo } from 'react'
import { Bundle, buildMapsLink, findPlaceLabel } from '../contracts/trip'

interface FoodPageProps {
  bundle: Bundle
}

function timeLabel(value: string | null): string {
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '彈性安排'
}

function highlightParts(value: string): { title: string; reason: string } {
  const separator = value.indexOf('：')
  if (separator < 0) return { title: value, reason: '' }
  return { title: value.slice(0, separator), reason: value.slice(separator + 1) }
}

export function FoodPage({ bundle }: FoodPageProps) {
  const placeGuides = useMemo(() => bundle.travel_assistant?.place_guides || {}, [bundle.travel_assistant])
  const mealGroups = useMemo(() => bundle.days.map((day, index) => ({
    dayNumber: index + 1,
    date: day.date,
    meals: day.items.filter((item) => item.kind === 'meal' && placeGuides[item.place_id]),
  })).filter((group) => group.meals.length > 0), [bundle.days, placeGuides])

  return (
    <section className="food-workspace" aria-label="餐飲與補給">
      <header className="page-intro food-intro">
        <div><p className="eyebrow">每日餐飲</p><h1>吃什麼，一眼就知道</h1><p>依日期整理用餐時間、推薦餐點、價格、排隊與停車資訊；點餐廳名稱即可在 Google Maps 開啟。</p></div>
      </header>

      <div className="food-day-groups">
        {mealGroups.map((group) => <section className="food-day" key={group.date}>
          <header><span>第 {group.dayNumber} 天</span><h2>{group.date}</h2></header>
          <div className="food-card-grid">{group.meals.map((meal) => {
            const name = findPlaceLabel(bundle.places, meal.place_id)
            const place = bundle.places?.find((candidate) => candidate.id === meal.place_id)
            const guide = placeGuides[meal.place_id]
            if (!guide) return null
            const parkingMapsQuery = (guide as typeof guide & { parkingMapsQuery?: string }).parkingMapsQuery
            return <article className="food-card" key={meal.id}>
              {place?.image_url ? <figure className="food-photo"><img src={place.image_url} alt={place.image_alt || name} loading="lazy" />{place.image_source_url ? <figcaption><a href={place.image_source_url} target="_blank" rel="noreferrer">圖片來源</a></figcaption> : null}</figure> : null}
              <div className="food-card-time">{timeLabel(meal.start_at)}</div>
              <h3><a href={buildMapsLink(place?.maps_query || name)} target="_blank" rel="noreferrer" aria-label={`${name} 在 Google Maps 開啟`}>{name}</a></h3>
              <>
                <dl><div><dt>預計用餐</dt><dd>{guide.duration}</dd></div><div><dt>預估花費</dt><dd>{guide.cost}</dd></div>{guide.hours ? <div><dt>營業時間</dt><dd>{guide.hours}</dd></div> : null}<div><dt>排隊與等候</dt><dd>{guide.queue}</dd></div><div><dt>停車建議</dt><dd>{guide.parking}</dd></div></dl>
                <div className="food-picks"><strong>推薦餐點與飲品</strong><ol>{guide.highlights.map((highlight) => { const parts = highlightParts(highlight); return <li key={highlight}><strong>{parts.title}</strong>{parts.reason ? <span>{parts.reason}</span> : null}</li> })}</ol></div>
                {parkingMapsQuery ? <a className="parking-map-link" href={buildMapsLink(parkingMapsQuery)} target="_blank" rel="noreferrer">開啟停車場地圖</a> : null}
                {guide.sourceUrl ? <a className="official-info-link" href={guide.sourceUrl} target="_blank" rel="noreferrer">官方網站</a> : null}
              </>
            </article>
          })}</div>
        </section>)}
      </div>
    </section>
  )
}
