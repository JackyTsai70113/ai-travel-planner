import { useMemo } from 'react'
import { Bundle, buildMapsLink, findPlaceLabel } from '../contracts/trip'
import { AWAJI_PLACE_GUIDES } from '../content/awaji-travel-guide'

interface FoodPageProps {
  bundle: Bundle
}

function timeLabel(value: string | null): string {
  return value?.match(/T(\d{2}:\d{2})/)?.[1] || '彈性安排'
}

export function FoodPage({ bundle }: FoodPageProps) {
  const mealGroups = useMemo(() => bundle.days.map((day) => ({
    date: day.date,
    meals: day.items.filter((item) => item.kind === 'meal'),
  })).filter((group) => group.meals.length > 0), [bundle.days])

  return (
    <section className="food-workspace" aria-label="餐飲與補給">
      <header className="page-intro food-intro">
        <div><p className="eyebrow">每日餐飲</p><h1>吃什麼，一眼就知道</h1><p>依日期整理用餐時間、推薦餐點、價格、排隊與停車資訊；點餐廳名稱即可在 Google Maps 開啟。</p></div>
      </header>

      <div className="food-day-groups">
        {mealGroups.map((group, dayIndex) => <section className="food-day" key={group.date}>
          <header><span>第 {dayIndex + 1} 天</span><h2>{group.date}</h2></header>
          <div className="food-card-grid">{group.meals.map((meal) => {
            const name = findPlaceLabel(bundle.places, meal.place_id)
            const place = bundle.places?.find((candidate) => candidate.id === meal.place_id)
            const guide = AWAJI_PLACE_GUIDES[meal.place_id]
            return <article className="food-card" key={meal.id}>
              <div className="food-card-time">{timeLabel(meal.start_at)}</div>
              <h3><a href={buildMapsLink(place?.maps_query || name)} target="_blank" rel="noreferrer" aria-label={`${name} 在 Google Maps 開啟`}>{name}<span aria-hidden="true">↗</span></a></h3>
              {guide ? <>
                <dl><div><dt>用餐時間</dt><dd>{guide.duration}</dd></div><div><dt>預算</dt><dd>{guide.cost}</dd></div><div><dt>排隊</dt><dd>{guide.queue}</dd></div><div><dt>停車</dt><dd>{guide.parking}</dd></div></dl>
                {guide.hours ? <p className="food-hours"><strong>營業時間</strong>{guide.hours}</p> : null}
                <div className="food-picks"><strong>推薦餐點與飲品</strong><ol>{guide.highlights.map((highlight) => <li key={highlight}>{highlight}</li>)}</ol></div>
                <a className="official-info-link" href={guide.sourceUrl} target="_blank" rel="noreferrer">查看官方資訊 ↗</a>
              </> : <p>這一餐以住宿內用餐為主，不需另找餐廳。</p>}
            </article>
          })}</div>
        </section>)}
      </div>
    </section>
  )
}
