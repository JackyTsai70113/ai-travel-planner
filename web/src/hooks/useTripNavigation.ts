import { useCallback, useEffect, useMemo, useState } from 'react'
import { parseRouteFromHash, SectionId, TripRoute, buildRoutePath } from '../app/route-registry'

interface UseTripNavigationOptions {
  defaultSection?: SectionId
  storageKey?: string
}

export function useTripNavigation(options: UseTripNavigationOptions = {}) {
  const defaultSection = options.defaultSection ?? 'overview'
  const storageKey = options.storageKey ?? 'trip:active:navigation:v1'

  const parse = useCallback(() => parseRouteFromHash(window.location.hash, defaultSection), [defaultSection])
  const [route, setRoute] = useState<TripRoute>(() => parse())

  useEffect(() => {
    const onChange = () => {
      const next = parse()
      setRoute(next)
      localStorage.setItem(storageKey, next.raw)
    }

    onChange()
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [parse, storageKey])

  const navigate = useCallback(
    (next: Partial<TripRoute>) => {
      const merged: TripRoute = {
        ...route,
        ...next,
        section: next.section ?? route.section,
        raw: '',
      }
      const nextHash = buildRoutePath(merged)
      window.location.hash = nextHash
    },
    [route],
  )

  const current = useMemo(() => route, [route])
  const lastNavigation = localStorage.getItem(storageKey) || ''

  return { current, navigate, lastNavigation }
}
