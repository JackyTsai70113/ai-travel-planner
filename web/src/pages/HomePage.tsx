import TripCatalogPage from '../features/trip-catalog'
import type { TripCatalogEntry, TripRegistrySections } from '../contracts/trip-registry'

type RouteSetter = (next: { route: 'home' | 'trip'; slug?: string }) => void

interface HomePageProps {
  catalog: TripCatalogEntry[]
  sections: TripRegistrySections
  setRoute: RouteSetter
  searchPlaceholder: string
}

export default function HomePage({ catalog, sections, setRoute, searchPlaceholder }: HomePageProps) {
  return (
    <main className="portal-page">
      <header className="portal-hero">
        <p className="trip-hero-eyebrow">日本旅程</p>
        <h1>AI Travel Planner</h1>
        <p>把已驗證的旅行資料，整理成可探索、可分享、可安心閱讀的日本旅程網站。</p>
        <small>頁面公開狀態與行程完成度分開呈現；公開預覽不代表行程已確認。</small>
      </header>
      <TripCatalogPage
        catalog={catalog}
        sections={sections}
        setRoute={setRoute}
        searchPlaceholder={searchPlaceholder}
      />
    </main>
  )
}
