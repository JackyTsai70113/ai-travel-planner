import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Bundle } from '../src/contracts/trip'
import { buildMapsDirectionsLink, buildRouteDirectionChunks } from '../src/lib/google-maps-links'
import { groupContiguousLegs, MapPage } from '../src/pages/MapPage'
import { ItineraryPage } from '../src/pages/ItineraryPage'
import { PackingPage } from '../src/pages/PackingPage'
import { buildReservationCalendarIcs } from '../src/pages/ReservationsPage'

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

const placeIds = ['a', 'b', 'c', 'd', 'e', 'f']
const placeNames = ['神戶機場', '淡路住宿', '洲本城', '鳴門公園', '神戶三宮', '神戶機場第二航廈']

const bundle: Bundle = {
  trip_id: 'awaji-test',
  title: '淡路五日',
  status: 'ok',
  local_timezone: 'Asia/Tokyo',
  date_range: { start_date: dates[0], end_date: dates[4] },
  traveler_profile: { adults: 2, children_count: 1, children_ages: [5] },
  selected: { hotel_place_ids: ['b'], flight_ids: [] },
  places: placeIds.map((id, index) => ({
    id,
    name: placeNames[index],
    maps_query: `${placeNames[index]} 日本`,
    ...(id === 'b' ? {
      opening_hours_note: '試算表記載 7:00–22:00；出發前一天重查。',
      parking: '試算表記載停車資訊；抵達前重查。',
      field_provenance: {
        opening_hours_note: {
          status: 'reported' as const,
          provider: 'Google Sheet',
          source_url: 'https://docs.google.com/spreadsheets/d/example/edit?gid=1',
        },
      },
    } : {}),
  })),
  days: dates.map((date, index) => ({
    date,
    summary: `第 ${index + 1} 日摘要`,
    items: [{
      id: `move-${placeIds[index]}-${placeIds[index + 1]}`,
      kind: 'transport',
      start_at: `${date}T10:00:00+09:00`,
      end_at: `${date}T10:45:00+09:00`,
      place_id: placeIds[index + 1],
      transport_leg_id: `leg-${placeIds[index]}-${placeIds[index + 1]}`,
    }, {
      id: `visit-${placeIds[index + 1]}`,
      kind: 'place',
      start_at: `${date}T10:45:00+09:00`,
      end_at: `${date}T12:15:00+09:00`,
      place_id: placeIds[index + 1],
      expected_stay_minutes: index === 0 ? 90 : null,
    }],
  })),
  transport_legs: dates.map((date, index) => ({
    id: `leg-${placeIds[index]}-${placeIds[index + 1]}`,
    mode: index === 4 ? 'bus' : 'car',
    status: 'estimated',
    from_place: placeIds[index],
    to_place: placeIds[index + 1],
    from_label: placeNames[index],
    to_label: placeNames[index + 1],
    departure_at: `${date}T10:00:00+09:00`,
    arrival_at: `${date}T10:45:00+09:00`,
    estimated_duration_minutes: 45,
    transfer_minutes: index === 0 ? 40 : 45,
    buffer_minutes: index === 0 ? 15 : null,
    note: index === 0 ? '若延誤 20 分鐘，直接前往住宿' : '出發前重查路況',
    source_url: 'https://example.com/source',
    source_refs: [`sheet-leg-${index + 1}`],
    provenance: {
      status: 'estimated',
      provider: 'Google Sheet',
      retrieved_at: '2026-08-23T00:00:00Z',
      confidence: 0.5,
    },
  })),
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
  beforeEach(() => {
    cleanup()
    localStorage.clear()
  })

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
    expect(screen.getByText('40 分鐘（規劃估計）')).toBeInTheDocument()
    expect(screen.getByText('15 分鐘')).toBeInTheDocument()
    expect(screen.getByText('90 分鐘')).toBeInTheDocument()
    expect(screen.getByText(/若延誤 20 分鐘/)).toBeInTheDocument()
    const routeLink = screen.getByRole('link', { name: '逐段導航' })
    expect(routeLink.getAttribute('href')).toContain('google.com/maps/dir/')
    fireEvent.click(screen.getByRole('button', { name: /Day 5/ }))
    expect(screen.getByRole('heading', { name: '第 5 日摘要' })).toBeInTheDocument()
    expect(screen.queryByText('尚無逐段資料')).not.toBeInTheDocument()
  })

  it('groups only contiguous legs with the same Google travel mode', () => {
    const base = bundle.transport_legs || []
    const first = base[0]
    const groups = groupContiguousLegs([
      first,
      { ...base[1], from_place: first.to_place, mode: 'drive' },
      { ...base[2], from_place: base[1].to_place, mode: 'bus' },
      { ...base[3], from_place: 'disconnected', mode: 'car' },
    ])
    expect(groups.map((group) => group.legs.length)).toEqual([2, 1, 1])
    expect(groups.map((group) => group.travelMode)).toEqual(['driving', 'transit', 'driving'])
  })

  it('limits mobile route chunks to five stops and preserves transit mode', () => {
    const stops = Array.from({ length: 9 }, (_, index) => ({ id: `s${index}`, label: `站 ${index}` }))
    const chunks = buildRouteDirectionChunks(stops, 'transit')
    expect(chunks.every((chunk) => chunk.waypoints.length <= 3)).toBe(true)
    expect(chunks.every((chunk) => [chunk.source, ...chunk.waypoints, chunk.destination].length <= 5)).toBe(true)
    expect(chunks[0].destination.id).toBe(chunks[1].source.id)
    expect(new URL(chunks[0].href).searchParams.get('travelmode')).toBe('transit')
  })

  it('exports reservation timestamps as UTC instead of browser-local wall time', () => {
    const ics = buildReservationCalendarIcs({
      id: 'pancake',
      day: '2026-08-28',
      time: '2026-08-28T17:45:00+09:00',
      name: '幸せのパンケーキ 淡路島テラス',
      place_id: 'b',
      kind: 'restaurant',
    })
    expect(ics).toContain('DTSTART:20260828T084500Z')
    expect(ics).toContain('DTEND:20260828T094500Z')
    expect(ics).not.toContain('DTSTART:20260828T164500')
  })

  it('keeps itinerary day navigation route-aware', () => {
    const onNavigate = vi.fn()
    render(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[0], raw: `today/${dates[0]}` }} onNavigate={onNavigate} />)
    expect(screen.getAllByRole('tab')).toHaveLength(5)
    expect(screen.getByRole('heading', { name: /神戶機場 → 淡路住宿/ })).toBeInTheDocument()
    expect(screen.getByText(/營業時間（待重查）/)).toBeInTheDocument()
    expect(screen.getByText(/停車（待重查）/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /D5/ }))
    expect(onNavigate).toHaveBeenCalledWith({ section: 'today', day: dates[4], item: undefined })
  })

  it('uses the bundle checklist and persists each checked item locally', async () => {
    const firstRender = render(<PackingPage bundle={bundle} />)
    expect(screen.getByText('確認電子機票')).toBeInTheDocument()
    expect(screen.queryByText('護照／身分文件')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /確認電子機票/ }))
    await waitFor(() => {
      const stored = localStorage.getItem('trip:awaji-test:checklist:v2')
      expect(stored).not.toBeNull()
      expect(JSON.parse(stored || '{}').data['sheet-ticket']).toBe(true)
    })
    firstRender.unmount()
    render(<PackingPage bundle={bundle} />)
    expect(screen.getByRole('checkbox', { name: /確認電子機票/ })).toBeChecked()
  })
})
