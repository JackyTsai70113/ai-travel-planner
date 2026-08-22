import { describe, expect, it } from 'vitest'
import { parseBundle } from '../src/contracts/trip'
import { buildRoutePath, parseRouteFromHash } from '../src/app/route-registry'
import { resolveBundleUrl, resolveRegistryUrl } from '../src/hooks/useBundleLoader'

const validBundle = {
  trip_id: 'trip-a', title: 'Trip A', status: 'ok', local_timezone: 'Asia/Tokyo',
  date_range: { start_date: '2026-01-01', end_date: '2026-01-02' }, days: [], reservations: [],
  budget: { currency: 'JPY', total: { amount: 0, currency: 'JPY' } }, validation: [],
  meta: { generated_at: '2026-01-01T00:00:00Z' },
}

describe('canonical frontend contracts', () => {
  it('accepts the minimum versioned bundle shape and rejects malformed data', () => {
    expect(parseBundle(validBundle).ok).toBe(true)
    expect(parseBundle({ ...validBundle, days: 'not-an-array' }).ok).toBe(false)
    expect(parseBundle({ ...validBundle, trip_id: '' }).ok).toBe(false)
  })

  it('round-trips day and item routes', () => {
    const path = buildRoutePath({ section: 'today', day: '2026-01-02', item: 'item/1' })
    expect(parseRouteFromHash(path, 'overview')).toMatchObject({ section: 'today', day: '2026-01-02', item: 'item/1' })
  })

  it('resolves one canonical bundle URL under project and root bases', () => {
    expect(resolveBundleUrl('/planner/', 'trips/trip-a')).toBe('http://localhost:3000/planner/trips/trip-a/public-bundle.json')
    expect(resolveBundleUrl('/', 'trips/trip-a')).toBe('http://localhost:3000/trips/trip-a/public-bundle.json')
  })

  it('keeps registry and bundle requests inside a relative GitHub Pages trip path', () => {
    const deployedPage = 'https://example.github.io/ai-travel-planner/trips/awaji-2026/'
    expect(resolveRegistryUrl('./', deployedPage)).toBe(`${deployedPage}trip-registry.json`)
    expect(resolveBundleUrl('./', 'trips/awaji-2026', deployedPage)).toBe(`${deployedPage}public-bundle.json`)
  })
})
