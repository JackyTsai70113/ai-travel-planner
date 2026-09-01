import { useCallback, useEffect, useMemo, useState } from 'react'
import TripShell from '../layouts/TripShell'
import { Bundle } from '../contracts/trip'
import { useBundleLoader } from '../hooks/useBundleLoader'
import { useTripNavigation } from '../hooks/useTripNavigation'
import {
  SECTION_DEFINITIONS,
  SectionId,
  TripRoute,
  parseSection,
  SECTION_BY_ID,
} from './route-registry'
import { OverviewPage } from '../pages/OverviewPage'
import { ItineraryPage } from '../pages/ItineraryPage'
import { ReservationsPage } from '../pages/ReservationsPage'
import { FoodPage } from '../pages/FoodPage'
import { PackingPage } from '../pages/PackingPage'
import { JapanesePage } from '../pages/JapanesePage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { TripStatusType } from '../layouts/TripShell'
import type { TripCatalogEntry } from '../contracts/trip-registry'

type AppStatusType =
  | 'loading'
  | 'invalid'
  | 'critical'
  | 'route-not-found'
  | 'normal'

interface TripAppProps {
  tripMeta?: TripCatalogEntry | null
  tripSlug?: string
}

function deriveDayFromRoute(bundle: Bundle, route: TripRoute): number | null {
  if (!route.day) return bundle.days.length ? 0 : null
  const numeric = Number(route.day)
  if (Number.isInteger(numeric) && numeric >= 1 && numeric <= bundle.days.length) return numeric - 1
  const index = bundle.days.findIndex((day) => day.date === route.day)
  return index >= 0 ? index : null
}

function resolveStatus(
  bundle: Bundle | null,
  status: string,
): AppStatusType {
  if (status === 'loading') return 'loading'
  if (!bundle) return 'invalid'
  if (bundle.validation.some((item) => item.severity === 'error')) return 'critical'
  if (status === 'error') return 'invalid'
  return 'normal'
}

export default function TripApp({ tripMeta = null, tripSlug }: TripAppProps) {
  const bundleLoader = useBundleLoader(tripSlug)
  const { current: route, navigate } = useTripNavigation({ defaultSection: 'overview' })
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [routeNotFound, setRouteNotFound] = useState(false)
  const pageTitleId = 'trip-page-title'

  const selectedSection = parseSection(route.section, 'overview')
  const isDayScopedSection = selectedSection === 'today'
  const requestedSection = route.raw
    ? (() => {
      try {
        return decodeURIComponent(route.raw.split('/')[0] || '')
      } catch {
        return ''
      }
    })()
    : ''
  const routeSectionNotFound = requestedSection ? !SECTION_BY_ID.has(requestedSection) : false

  const shellStatus: TripStatusType = useMemo<TripStatusType>(() => {
    if (routeNotFound) return 'route-not-found'
    const base = resolveStatus(bundleLoader.bundle, bundleLoader.status)
    if (base === 'loading') return 'loading'
    if (base === 'invalid') return 'invalid'
    if (base === 'critical') return 'critical'
    return 'normal'
  }, [bundleLoader.bundle, bundleLoader.status, routeNotFound])

  const normalizeDay = useCallback(
    (candidate: string | undefined) => {
      if (!candidate || !bundleLoader.bundle) return undefined
      if (bundleLoader.bundle.days.some((day) => day.date === candidate)) return candidate
      const dayIndex = Number(candidate)
      if (!Number.isInteger(dayIndex) || dayIndex < 1) return undefined
      return bundleLoader.bundle.days[dayIndex - 1]?.date
    },
    [bundleLoader.bundle],
  )

  const activeDay = useMemo(() => {
    if (!bundleLoader.bundle || !isDayScopedSection) return undefined
    const fromRoute = normalizeDay(route.day)
    return bundleLoader.bundle.days.find((day) => day.date === fromRoute) || bundleLoader.bundle.days[0]
  }, [bundleLoader.bundle, isDayScopedSection, route.day, normalizeDay])

  useEffect(() => {
    if (!isDayScopedSection && !routeSectionNotFound) {
      setRouteNotFound(false)
      return
    }
    if (routeSectionNotFound) {
      setRouteNotFound(true)
      return
    }
    const selectedDay = bundleLoader.bundle ? deriveDayFromRoute(bundleLoader.bundle, route) : null
    const hasInvalidDay = route.day ? selectedDay === null : false
    setRouteNotFound(hasInvalidDay)
  }, [bundleLoader.bundle, isDayScopedSection, route, routeSectionNotFound])

  const defaultItineraryDay = useMemo(() => {
    if (!bundleLoader.bundle) return undefined
    return normalizeDay(route.day) || bundleLoader.bundle.days[0]?.date
  }, [bundleLoader.bundle, normalizeDay, route.day])

  const effectiveRoute = useMemo<TripRoute>(() => {
    if (!isDayScopedSection) return route
    return {
      ...route,
      section: selectedSection,
      day: activeDay?.date || defaultItineraryDay,
      raw: route.raw,
    }
  }, [activeDay?.date, defaultItineraryDay, isDayScopedSection, route, selectedSection])

  const gotoSection = useCallback(
    (nextSection: string) => {
      const dayAwareSection = nextSection === 'today'
      const next: Partial<TripRoute> = { section: nextSection as SectionId }
      if (dayAwareSection && defaultItineraryDay) {
        next.day = defaultItineraryDay
      } else if (!dayAwareSection) {
        next.day = undefined
      }
      navigate(next)
    },
    [defaultItineraryDay, navigate],
  )

  const gotoRoute = useCallback((next: Partial<TripRoute>) => navigate(next), [navigate])

  const mainSection = useMemo(() => {
    if (routeNotFound) {
      return <NotFoundPage path={effectiveRoute.raw || 'n/a'} />
    }
    const bundle = bundleLoader.bundle

    if (!bundle && selectedSection !== 'overview') {
      return (
        <section className="card">
          <h2>資料載入中…</h2>
          <p className="muted">正在載入行程資料，請稍後。</p>
        </section>
      )
    }

    if (selectedSection === 'overview') {
      return <OverviewPage bundle={bundle} trip={tripMeta} />
    }
    if (!bundle) return <OverviewPage bundle={null} trip={tripMeta} />

    if (selectedSection === 'today') {
      return (
        <ItineraryPage
          bundle={bundle}
          route={{
            ...effectiveRoute,
            day: effectiveRoute.day || bundle.days[0]?.date,
            section: 'today',
            raw: effectiveRoute.raw,
          }}
          onNavigate={gotoRoute}
        />
      )
    }
    if (selectedSection === 'reservation') {
      return <ReservationsPage bundle={bundle} />
    }
    if (selectedSection === 'food') {
      return <FoodPage bundle={bundle} />
    }
    if (selectedSection === 'packing') {
      return <PackingPage bundle={bundle} />
    }
    if (selectedSection === 'japanese') {
      return <JapanesePage />
    }
    return <NotFoundPage path={effectiveRoute.raw || 'n/a'} />
  }, [bundleLoader.bundle, effectiveRoute, gotoRoute, routeNotFound, selectedSection, tripMeta])

  const renderBundleLoading = !bundleLoader.bundle && shellStatus === 'loading'

  if (renderBundleLoading) {
    return (
      <TripShell
        bundle={null}
        fallbackTitle={tripMeta?.title}
        shellStatus="loading"
        pageTitleId={pageTitleId}
        sections={SECTION_DEFINITIONS}
        activeSection={selectedSection}
        onNavigateSection={gotoSection}
        isDrawerOpen={drawerOpen}
        setDrawerOpen={setDrawerOpen}
        >
          <section className="card">
            <h2>讀取行程中…</h2>
          </section>
      </TripShell>
    )
  }

  return (
    <TripShell
      bundle={bundleLoader.bundle}
      fallbackTitle={tripMeta?.title}
      shellStatus={shellStatus}
      pageTitleId={pageTitleId}
      sections={SECTION_DEFINITIONS}
      activeSection={selectedSection}
      onNavigateSection={gotoSection}
      isDrawerOpen={drawerOpen}
      setDrawerOpen={setDrawerOpen}
    >
      {mainSection}
    </TripShell>
  )
}
