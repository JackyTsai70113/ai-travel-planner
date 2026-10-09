import { describe, expect, it, vi } from 'vitest'
import { parseBundle } from '../src/contracts/trip'
import { buildRoutePath, parseRouteFromHash } from '../src/app/route-registry'
import { resolveBundleUrl, resolveRegistryUrl } from '../src/hooks/useBundleLoader'
import { googleMapsHrefForPlace } from '../src/lib/google-maps-links'
import { fetchFresh } from '../src/lib/fresh-fetch'

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
    expect(parseBundle({ ...validBundle, place_details_api_base_url: 'http://example.test/api/public/trips' }).ok).toBe(false)
    expect(parseBundle({ ...validBundle, place_details_api_base_url: 'https://example.test/untrusted' }).ok).toBe(false)
    expect(parseBundle({ ...validBundle, place_details_api_base_url: 'https://example.test/api/public/trips' }).ok).toBe(true)
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
    expect(resolveRegistryUrl('./', deployedPage)).toBe('https://example.github.io/ai-travel-planner/trip-registry.json')
    expect(resolveBundleUrl('./', 'trips/awaji-2026', deployedPage)).toBe(`${deployedPage}public-bundle.json`)
  })

  it('bypasses browser caches for mutable public trip data', async () => {
    const response = { ok: true } as Response
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response)

    await fetchFresh('https://example.github.io/ai-travel-planner/trip-registry.json')

    expect(fetchSpy).toHaveBeenCalledWith('https://example.github.io/ai-travel-planner/trip-registry.json', { cache: 'no-store' })
    fetchSpy.mockRestore()
  })

  it('builds a direct Google Maps place link from a retained Place ID without coordinates', () => {
    const target = new URL(googleMapsHrefForPlace({ google_place_id: 'ChIJ-place' }))
    expect(target.hostname).toBe('www.google.com')
    expect(target.pathname).toBe('/maps/search/')
    expect(target.searchParams.get('query_place_id')).toBe('ChIJ-place')
    expect(target.searchParams.has('query')).toBe(true)
  })
})
