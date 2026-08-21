import { TripRoute } from '../app/route-registry'

interface MapPageProps {
  route: TripRoute
  currentDay?: string
}

export function MapPage({ route, currentDay }: MapPageProps) {
  return (
    <section className="card" aria-label="地圖與自駕">
      <h2>地圖與自駕</h2>
      <p>建議用「{route.day || currentDay || '今日'}」行程直接開啟對應地圖。</p>
      <p>
        行動版可直接呼叫 Google Maps；桌面版建議先開新分頁規劃。
      </p>
      <a href="https://maps.google.com" target="_blank" rel="noreferrer">
        開啟 Google Maps
      </a>
    </section>
  )
}
