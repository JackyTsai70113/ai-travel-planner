import { useCallback, useEffect, useMemo, useState } from 'react'
import TripShell from '../layouts/TripShell'
import { Bundle, toFriendlyStatus } from '../contracts/trip'
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
import { TidesPage } from '../pages/TidesPage'
import { FoodPage } from '../pages/FoodPage'
import { LodgingPage } from '../pages/LodgingPage'
import { HandbookPage } from '../pages/HandbookPage'
import { PackingPage } from '../pages/PackingPage'
import { BudgetPage } from '../pages/BudgetPage'
import { MapPage } from '../pages/MapPage'
import { JapanesePage } from '../pages/JapanesePage'
import { SourcesPage } from '../pages/SourcesPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { TripStatusType } from '../layouts/TripShell'
import type { TripCatalogEntry } from '../contracts/trip-registry'

type AppStatusType =
  | 'loading'
  | 'invalid'
  | 'critical'
  | 'offline-cache'
  | 'offline-no-cache'
  | 'route-not-found'
  | 'normal'

interface TripAppProps {
  tripMeta?: TripCatalogEntry | null
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
  isOnline: boolean,
): AppStatusType {
  if (status === 'loading') return 'loading'
  if (!bundle) {
    return isOnline ? 'invalid' : 'offline-no-cache'
  }
  if (bundle.validation.some((item) => item.severity === 'error')) return 'critical'
  if (!isOnline) return 'offline-cache'
  if (status === 'error') return 'invalid'
  return 'normal'
}

export default function TripApp({ tripMeta = null }: TripAppProps) {
  const bundleLoader = useBundleLoader()
  const { current: route, navigate } = useTripNavigation({ defaultSection: 'overview' })
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [routeNotFound, setRouteNotFound] = useState(false)
  const pageTitleId = 'trip-page-title'

  const selectedSection = parseSection(route.section, 'overview')
  const isDayScopedSection = selectedSection === 'today' || selectedSection === 'tides'
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
    const base = resolveStatus(bundleLoader.bundle, bundleLoader.status, bundleLoader.isOnline)
    if (base === 'loading') return 'loading'
    if (base === 'invalid') return 'invalid'
    if (base === 'offline-no-cache') return 'offline-no-cache'
    if (base === 'offline-cache') return 'offline-cache'
    if (base === 'critical') return 'critical'
    if (bundleLoader.isUpdateAvailable) return 'newer-version'
    return 'normal'
  }, [bundleLoader.bundle, bundleLoader.isOnline, bundleLoader.isUpdateAvailable, bundleLoader.status, routeNotFound])

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
  }, [bundleLoader.bundle, isDayScopedSection, route.day, route.section, routeSectionNotFound])

  const itineraryDayFromLastNavigation = useMemo(() => {
    if (!bundleLoader.bundle) return undefined
    if (route.day) return normalizeDay(route.day)
    const saved = localStorage.getItem(`golden_trip_last_day_${selectedSection}`)
    return normalizeDay(saved || undefined) || bundleLoader.bundle.days[0]?.date
  }, [bundleLoader.bundle, normalizeDay, route.day, selectedSection])

  const effectiveRoute = useMemo<TripRoute>(() => {
    if (!isDayScopedSection) return route
    return {
      ...route,
      section: selectedSection,
      day: activeDay?.date || itineraryDayFromLastNavigation,
      raw: route.raw,
    }
  }, [activeDay?.date, itineraryDayFromLastNavigation, isDayScopedSection, route, selectedSection])

  useEffect(() => {
    if (!activeDay) return
    if (selectedSection === 'today') {
      localStorage.setItem('golden_trip_last_day_today', activeDay.date)
    }
    if (selectedSection === 'tides') {
      localStorage.setItem('golden_trip_last_day_tides', activeDay.date)
    }
  }, [activeDay, selectedSection])

  const gotoSection = useCallback(
    (nextSection: string) => {
      const dayAwareSection = nextSection === 'today' || nextSection === 'tides'
      const next: Partial<TripRoute> = { section: nextSection as SectionId }
      if (dayAwareSection && itineraryDayFromLastNavigation) {
        next.day = itineraryDayFromLastNavigation
      } else if (!dayAwareSection) {
        next.day = undefined
      }
      navigate(next)
    },
    [itineraryDayFromLastNavigation, navigate],
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
    if (selectedSection === 'map') {
      return <MapPage route={effectiveRoute} currentDay={effectiveRoute.day || itineraryDayFromLastNavigation} />
    }
    if (selectedSection === 'reservation') {
      return <ReservationsPage bundle={bundle} />
    }
    if (selectedSection === 'tides') {
      return <TidesPage />
    }
    if (selectedSection === 'food') {
      return <FoodPage />
    }
    if (selectedSection === 'lodging') {
      return <LodgingPage />
    }
    if (selectedSection === 'handbook') {
      return <HandbookPage bundle={bundle} />
    }
    if (selectedSection === 'packing') {
      return <PackingPage bundle={bundle} />
    }
    if (selectedSection === 'budget') {
      return <BudgetPage bundle={bundle} />
    }
    if (selectedSection === 'japanese') {
      return <JapanesePage />
    }
    if (selectedSection === 'sources') {
      return <SourcesPage bundle={bundle} />
    }
    return <NotFoundPage path={effectiveRoute.raw || 'n/a'} />
  }, [bundleLoader.bundle, effectiveRoute, gotoRoute, itineraryDayFromLastNavigation, routeNotFound, selectedSection, tripMeta])

  const statusLabel = toFriendlyStatus(bundleLoader.bundle?.status || 'warning')
  const renderBundleLoading = !bundleLoader.bundle && shellStatus === 'loading'
  const tripVersion = bundleLoader.bundle?.meta?.generated_at || '--'

  const titleInfo = useMemo(() => `行程狀態：${statusLabel}`, [statusLabel])

  if (renderBundleLoading) {
    return (
      <TripShell
        bundle={null}
        shellStatus="loading"
        tripVersion={tripVersion}
        pageTitleId={pageTitleId}
        sections={SECTION_DEFINITIONS}
        activeSection={selectedSection}
        onNavigateSection={gotoSection}
        onRetry={() => {
          window.location.reload()
        }}
        isDrawerOpen={drawerOpen}
        setDrawerOpen={setDrawerOpen}
      >
        <section className="card">
          <h2>讀取行程中…</h2>
          <p className="muted">{bundleLoader.status}</p>
        </section>
      </TripShell>
    )
  }

  return (
    <TripShell
      bundle={bundleLoader.bundle}
      shellStatus={shellStatus}
      tripVersion={tripVersion}
      pageTitleId={pageTitleId}
      sections={SECTION_DEFINITIONS}
      activeSection={selectedSection}
      onNavigateSection={gotoSection}
      onRetry={() => {
        window.location.reload()
      }}
      isDrawerOpen={drawerOpen}
      setDrawerOpen={setDrawerOpen}
    >
      <p className="muted">
        {titleInfo}
        {shellStatus === 'route-not-found' ? '｜頁面路徑不存在，將導向可存取頁' : ''}
      </p>
      {mainSection}
    </TripShell>
  )
}
