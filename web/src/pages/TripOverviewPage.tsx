import type { PublicTripBundle, TripCatalogEntry } from '../contracts/trip-registry'
import TripLandingOverview from '../features/trip-landing'

type RouteSetter = (next: { route: 'home' | 'trip'; slug?: string }) => void

type SwUiStatus = 'unknown' | 'registering' | 'ready' | 'failed' | 'unsupported'

interface TripOverviewPageProps {
  route: { route: 'home' | 'trip'; slug?: string }
  setRoute: RouteSetter
  trip: TripCatalogEntry | null | undefined
  bundle: PublicTripBundle | null
  swStatus: { status: SwUiStatus; message: string }
}

export default function TripOverviewPage({ route, setRoute, trip, bundle, swStatus }: TripOverviewPageProps) {
  if (route.route !== 'trip') return null
  const error = bundle ? '' : '資料載入中'
  return (
    <TripLandingOverview
      trip={trip || null}
      bundle={bundle}
      error={error}
      setRoute={setRoute}
      swStatus={swStatus}
    />
  )
}
