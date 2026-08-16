import { useMemo } from 'react'
import { Bundle, findPlaceLabel } from '../contracts/trip'
import { buildMapsLink } from '../contracts/trip'
import { buildRoutePath } from '../app/route-registry'

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
        <p>顯示行程中公開可映射的「餐飲」節點；其餘欄位留待未來證據補齊。</p>
      </header>

      <p className="shell-message">資料版本：{bundle.meta.generated_at}</p>

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
                    <span className="hub-status estimated">{meal.start_at ? 'estimated' : 'unverified'}</span>
                    <h4>{findPlaceLabel(bundle.places, meal.place_id)}</h4>
                  </div>
                  <p>時段：{meal.start_at ? new Date(meal.start_at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' }) : '待補'}</p>
                  {meal.notes ? <p>備註：{meal.notes}</p> : <p>備註：public-safe 未提供</p>}
                  <div className="hub-actions">
                    <a className="hub-inline-button" href={buildRoutePath({ section: 'today', day: group.date, item: meal.id })}>
                      回行程
                    </a>
                    <a className="hub-inline-button" href={buildMapsLink(findPlaceLabel(bundle.places, meal.place_id))} target="_blank" rel="noreferrer">
                      導航
                    </a>
                    <button
                      type="button"
                      onClick={() =>
                        navigator.clipboard.writeText(`餐食：${findPlaceLabel(bundle.places, meal.place_id)}（${group.date}）`)
                      }
                    >
                      複製餐廳
                    </button>
                  </div>
                  <p className="hub-meta">open status: public-safe 未提供 / queue risk: 未提供 / 替代方案：待補</p>
                </li>
              ))}
            </ul>
          </section>
        ))
      ) : (
        <p className="hub-empty">
          目前行程公開資料尚未提供餐廳明細、排隊風險、停靠補給策略。請以行程原始項目與景點頁備援。
        </p>
      )}
    </section>
  )
}

