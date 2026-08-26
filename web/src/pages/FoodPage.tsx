import { useMemo } from 'react'
import { Bundle, buildMapsLink, findPlaceLabel } from '../contracts/trip'
import { MapPinLink } from '../components/MapPinLink'
import { decisionCopy } from '../lib/decision-copy'
import { googleMapsHrefForPlace } from '../lib/google-maps-links'
import { usableOfficialHref } from '../lib/official-links'

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
        <div><p className="eyebrow">每日餐飲</p><h1>吃什麼，一眼就知道</h1></div>
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
            const mapHref = parkingMapsQuery ? buildMapsLink(parkingMapsQuery) : googleMapsHrefForPlace(place, name)
            const officialHref = usableOfficialHref(guide.sourceUrl || place?.official_url)
            const facts = [
              { label: '預計用餐', value: decisionCopy(guide.duration) },
              { label: '預估花費', value: decisionCopy(guide.cost) },
              { label: '營業時間', value: decisionCopy(guide.hours) },
              { label: '排隊與等候', value: decisionCopy(guide.queue) },
              { label: '停車', value: decisionCopy(guide.parking) },
            ].filter((fact): fact is { label: string; value: string } => Boolean(fact.value))
            return <article className="food-card" key={meal.id}>
              {place?.image_url ? <figure className="food-photo"><img src={place.image_url} alt={place.image_alt || name} loading="lazy" />{place.image_source_url ? <figcaption><a href={place.image_source_url} target="_blank" rel="noreferrer">圖片來源</a></figcaption> : null}</figure> : null}
              <div className="food-card-time">{timeLabel(meal.start_at)}</div>
              <div className="food-place-heading"><h3>{officialHref ? <a className="official-title-link" href={officialHref} target="_blank" rel="noreferrer">{name}</a> : name}</h3><MapPinLink href={mapHref} label={`在 Google Maps 開啟 ${parkingMapsQuery ? `${name} 停車場` : name}`} /></div>
              <>
                {facts.length > 0 ? <dl>{facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl> : null}
                <div className="food-picks"><strong>推薦餐點與飲品</strong><ol>{guide.highlights.map((highlight) => { const parts = highlightParts(highlight); return <li key={highlight}><strong>{parts.title}</strong>{parts.reason ? <span>{parts.reason}</span> : null}</li> })}</ol></div>
              </>
            </article>
          })}</div>
        </section>)}
      </div>
    </section>
  )
}
