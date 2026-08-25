import { useMemo } from 'react'
import { Bundle, findPlaceLabel } from '../contracts/trip'
import { MapPinIcon } from '../design-system/primitives/MapPinIcon'
import { buildMapsSearchLink } from '../lib/google-maps-links'

interface FoodPageProps {
  bundle: Bundle
}

export function FoodPage({ bundle }: FoodPageProps) {
  const mealGroups = useMemo(() => {
    return bundle.days
      .map((day) => ({
        date: day.date,
        meals: day.items.filter((item) => item.kind === 'meal'),
      }))
      .filter((group) => group.meals.length > 0)
  }, [bundle.days])

  return (
    <section className="card hub-card-wrapper" aria-label="餐飲與補給">
      <header className="hub-header">
        <h2>餐飲與補給</h2>
        <p>依每日行程整理用餐時間與地點。</p>
      </header>

      <div className="hub-stats">
        <p>餐食段落：{mealGroups.reduce((sum, group) => sum + group.meals.length, 0)}</p>
        <p>可回溯日程：{mealGroups.length} 天</p>
      </div>

      {mealGroups.length > 0 ? (
        mealGroups.map((group) => (
          <section className="hub-section" key={group.date}>
            <h3>{group.date}</h3>
            <ul className="hub-items">
              {group.meals.map((meal) => (
                <li className="hub-item" key={meal.id}>
                  <div className="hub-item-row">
                    <h4>{findPlaceLabel(bundle.places, meal.place_id)}<a className="hub-map-link" href={buildMapsSearchLink(findPlaceLabel(bundle.places, meal.place_id))} target="_blank" rel="noreferrer" aria-label={`${findPlaceLabel(bundle.places, meal.place_id)} 在 Google Maps 開啟`} title="在 Google Maps 開啟"><MapPinIcon /></a></h4>
                  </div>
                  <p>用餐時間：{meal.start_at ? new Date(meal.start_at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' }) : '—'}</p>
                </li>
              ))}
            </ul>
          </section>
        ))
      ) : (
        <p className="hub-empty">
          目前沒有餐飲節點。
        </p>
      )}
    </section>
  )
}
