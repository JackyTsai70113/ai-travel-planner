import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Bundle, findPlaceLabel } from '../src/contracts/trip'
import { useLivePlaceDetails } from '../src/hooks/useLivePlaceDetails'

const bundle = {
  trip_id: 'demo-trip', title: '倉敷', status: 'warning', local_timezone: 'Asia/Tokyo',
  date_range: { start_date: '2026-11-01', end_date: '2026-11-01' },
  traveler_profile: { adults: 2, children_count: 0, children_ages: [] },
  selected: { hotel_place_ids: [], flight_ids: [] },
  days: [{ date: '2026-11-01', summary: '', items: [
    { id: 'poi', kind: 'visit', place_id: 'poi-place', start_at: null, end_at: null },
  ] }],
  places: [{ id: 'poi-place', google_place_id: 'ChIJ-place' }],
  reservations: [], preferences: { hard_constraints: [], soft_preferences: [] },
  budget: { currency: 'JPY', total: { amount: 0, currency: 'JPY' }, categories: {} },
  validation: [], meta: { generated_at: '2026-10-09T00:00:00Z' },
  place_details_api_base_url: 'https://ai-traveller.example.test/api/public/trips',
} as Bundle

function PlaceLabel() {
  const result = useLivePlaceDetails(bundle, 'demo-trip', 'today', '2026-11-01')
  return <p>{findPlaceLabel(result.bundle?.places, 'poi-place')}</p>
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('public Google place labels', () => {
  it('renders live names with no-store and graceful fallback when lookup fails', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'available', name: '倉敷美觀地區', attribution: 'Google Maps',
        third_party_attributions: [],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<PlaceLabel />)

    await waitFor(() => expect(screen.getByText('倉敷美觀地區')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith(
      'https://ai-traveller.example.test/api/public/trips/demo-trip/places/ChIJ-place',
      { method: 'GET', cache: 'no-store', credentials: 'omit' },
    )
  })

  it('shows an unavailable state and does not invent a place name', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(<PlaceLabel />)

    await waitFor(() => expect(screen.getByText('Google Maps 地點名稱暫時無法載入')).toBeInTheDocument())
    expect(screen.queryByText('倉敷美觀地區')).not.toBeInTheDocument()
  })
})
