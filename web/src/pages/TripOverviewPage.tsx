import type { TripCatalogEntry } from '../contracts/trip-registry'
import type { Bundle } from '../contracts/trip'
import TripLandingOverview from '../features/trip-landing'

type RouteSetter = (next: { route: 'home' | 'trip'; slug?: string }) => void

interface TripOverviewPageProps {
  route: { route: 'trip'; slug?: string }
  setRoute: RouteSetter
  trip: TripCatalogEntry | null | undefined
  bundle: Bundle | null
  bundleLoading: boolean
  bundleError: string
  swStatus: { status: 'unknown' | 'registering' | 'ready' | 'failed' | 'unsupported'; message: string }
}

export default function TripOverviewPage({ route, setRoute, trip, bundle }: TripOverviewPageProps) {
  if (route.route !== 'trip') return null
  return (
    <TripLandingOverview
      trip={trip || null}
      bundle={bundle}
      error={bundle && typeof bundle === 'object' ? '' : ''}
      setRoute={setRoute}
    />
  )
}
