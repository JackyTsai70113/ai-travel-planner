import { describe, expect, it } from 'vitest'
import { Bundle } from '../src/contracts/trip'
import { scheduledPlaceIdsForSection } from '../src/hooks/useLivePlaceDetails'

const bundle = {
  trip_id: 'demo-trip',
  title: 'Demo',
  status: 'warning',
  local_timezone: 'Asia/Tokyo',
  date_range: { start_date: '2026-11-01', end_date: '2026-11-02' },
  traveler_profile: { adults: 2, children_count: 0, children_ages: [] },
  selected: { hotel_place_ids: [], flight_ids: [] },
  days: [
    { date: '2026-11-01', summary: '', items: [
      { id: 'breakfast', kind: 'meal', place_id: 'breakfast-place', start_at: null, end_at: null },
      { id: 'poi', kind: 'visit', place_id: 'poi-place', start_at: null, end_at: null },
    ] },
    { date: '2026-11-02', summary: '', items: [
      { id: 'dinner', kind: 'meal', place_id: 'dinner-place', start_at: null, end_at: null },
      { id: 'named', kind: 'visit', place_id: 'already-named', start_at: null, end_at: null },
    ] },
  ],
  places: [
    { id: 'breakfast-place', google_place_id: 'ChIJbreakfast' },
    { id: 'poi-place', google_place_id: 'ChIJpoi' },
    { id: 'dinner-place', google_place_id: 'ChIJDinner' },
    { id: 'already-named', google_place_id: 'ChIJnamed', name: 'User supplied name' },
    { id: 'unselected', google_place_id: 'ChIJunselected' },
  ],
  reservations: [],
  preferences: { hard_constraints: [], soft_preferences: [] },
  budget: { currency: 'JPY', total: { amount: 0, currency: 'JPY' }, categories: {} },
  validation: [],
  meta: { generated_at: '2026-10-09T00:00:00Z' },
} as Bundle

describe('scheduled public place name lookup', () => {
  it('looks up only the active day places that do not already have a name', () => {
    expect(scheduledPlaceIdsForSection(bundle, 'today', '2026-11-01')).toEqual(['breakfast-place', 'poi-place'])
  })

  it('looks up only scheduled meal places on the food page', () => {
    expect(scheduledPlaceIdsForSection(bundle, 'food')).toEqual(['breakfast-place', 'dinner-place'])
  })

  it('does not query unselected candidates or independently named places', () => {
    expect(scheduledPlaceIdsForSection(bundle, 'overview')).not.toContain('unselected')
    expect(scheduledPlaceIdsForSection(bundle, 'today', '2026-11-02')).not.toContain('already-named')
  })
})
