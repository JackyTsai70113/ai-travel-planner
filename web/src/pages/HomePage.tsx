import TripCatalogPage from '../features/trip-catalog'
import type { TripCatalogEntry, TripCatalogSections } from '../contracts/trip-registry'

type RouteSetter = (next: { route: 'home' | 'trip'; slug?: string }) => void

interface HomePageProps {
  catalog: TripCatalogEntry[]
  sections: TripCatalogSections
  setRoute: RouteSetter
  searchPlaceholder: string
}

export default function HomePage({ catalog, sections, setRoute, searchPlaceholder }: HomePageProps) {
  return (
    <TripCatalogPage
      catalog={catalog}
      sections={sections}
      setRoute={setRoute}
      searchPlaceholder={searchPlaceholder}
    />
  )
}
