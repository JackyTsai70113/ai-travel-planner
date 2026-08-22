import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Bundle } from '../src/contracts/trip'
import { buildMapsDirectionsLink } from '../src/lib/google-maps-links'
import { MapPage } from '../src/pages/MapPage'
import { ItineraryPage } from '../src/pages/ItineraryPage'
import { PackingPage } from '../src/pages/PackingPage'

const dates = ['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31']
const storage = new Map<string, string>()
const localStorageMock: Storage = {
  get length() { return storage.size },
  clear: () => storage.clear(),
  getItem: (key) => storage.get(key) ?? null,
  key: (index) => [...storage.keys()][index] ?? null,
  removeItem: (key) => { storage.delete(key) },
  setItem: (key, value) => { storage.set(key, String(value)) },
}

const bundle: Bundle = {
  trip_id: 'awaji-test',
  title: '淡路五日',
  status: 'ok',
  local_timezone: 'Asia/Tokyo',
  date_range: { start_date: dates[0], end_date: dates[4] },
  traveler_profile: { adults: 2, children_count: 1, children_ages: [5] },
  selected: { hotel_place_ids: ['hotel'], flight_ids: [] },
  places: [
    { id: 'a', name: '神戶機場', maps_query: 'Kobe Airport' },
    { id: 'b', name: '淡路住宿', maps_query: 'Awaji Hotel' },
    { id: 'hotel', name: '測試住宿', address: '日本測試地址' },
  ],
  days: dates.map((date, index) => ({
    date,
    summary: `第 ${index + 1} 日摘要`,
    items: index === 0 ? [{
      id: 'move-a-b',
      kind: 'transport',
      start_at: `${date}T10:00:00+09:00`,
      end_at: `${date}T10:45:00+09:00`,
      place_id: 'b',
      transport_leg_id: 'leg-a-b',
      buffer_minutes: 15,
    }] : [],
  })),
  transport_legs: [{
    id: 'leg-a-b',
    mode: 'car',
    status: 'estimated',
    from_place: 'a',
    to_place: 'b',
    from_label: '神戶機場',
    to_label: '淡路住宿',
    departure_at: '2026-08-27T10:00:00+09:00',
    arrival_at: '2026-08-27T10:45:00+09:00',
    estimated_duration_minutes: 45,
    note: '若延誤 20 分鐘，直接前往住宿',
    source_url: 'https://example.com/source',
  }],
  operations: {
    pretrip_checklist: [{
      id: 'sheet-ticket',
      timing: '出發前一週',
      item: '確認電子機票',
      action: '下載離線副本',
      fallback: '到航空公司櫃台確認',
      contact: 'https://example.com/ticket',
    }],
  },
  reservations: [],
  preferences: { hard_constraints: [], soft_preferences: [] },
  budget: { currency: 'JPY', total: { amount: 0, currency: 'JPY' }, categories: {} },
  validation: [],
  meta: { generated_at: '2026-08-23T00:00:00Z' },
}

describe('Issue 97 travel handbook', () => {
  beforeAll(() => Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: localStorageMock }))
  beforeEach(() => localStorage.clear())

  it('builds a Google Maps directions URL without an API key', () => {
    const href = buildMapsDirectionsLink([
      { label: '神戶機場', mapsQuery: 'Kobe Airport' },
      { label: '淡路住宿', mapsQuery: 'Awaji Hotel' },
    ])
    const url = new URL(href)
    expect(url.pathname).toBe('/maps/dir/')
    expect(url.searchParams.get('api')).toBe('1')
    expect(url.searchParams.get('origin')).toBe('Kobe Airport')
    expect(url.searchParams.get('destination')).toBe('Awaji Hotel')
    expect(url.searchParams.get('travelmode')).toBe('driving')
    expect(url.searchParams.has('key')).toBe(false)
  })

  it('shows leg analysis and switches across all five days', () => {
    render(<MapPage bundle={bundle} route={{ section: 'map', raw: 'map' }} currentDay={dates[0]} />)
    expect(screen.getAllByRole('button', { name: /Day/ })).toHaveLength(5)
    expect(screen.getByText('神戶機場')).toBeInTheDocument()
    expect(screen.getByText('淡路住宿')).toBeInTheDocument()
    expect(screen.getByText('預估 45 分鐘')).toBeInTheDocument()
    expect(screen.getByText(/若延誤 20 分鐘/)).toBeInTheDocument()
    const routeLink = screen.getByRole('link', { name: '逐段導航' })
    expect(routeLink.getAttribute('href')).toContain('google.com/maps/dir/')
    fireEvent.click(screen.getByRole('button', { name: /Day 5/ }))
    expect(screen.getByRole('heading', { name: '第 5 日摘要' })).toBeInTheDocument()
  })

  it('keeps itinerary day navigation route-aware', () => {
    const onNavigate = vi.fn()
    render(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[0], raw: `today/${dates[0]}` }} onNavigate={onNavigate} />)
    expect(screen.getAllByRole('tab')).toHaveLength(5)
    expect(screen.getByRole('heading', { name: /神戶機場 → 淡路住宿/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /D5/ }))
    expect(onNavigate).toHaveBeenCalledWith({ section: 'today', day: dates[4], item: undefined })
  })

  it('uses the bundle checklist and persists each checked item locally', async () => {
    render(<PackingPage bundle={bundle} />)
    expect(screen.getByText('確認電子機票')).toBeInTheDocument()
    expect(screen.queryByText('護照／身分文件')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /確認電子機票/ }))
    await waitFor(() => {
      const stored = localStorage.getItem('trip:awaji-test:checklist:v2')
      expect(stored).not.toBeNull()
      expect(JSON.parse(stored || '{}').data['sheet-ticket']).toBe(true)
    })
  })
})
