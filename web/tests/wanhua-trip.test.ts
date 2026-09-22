import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseBundle } from '../src/contracts/trip'
import { isCatalogEntry } from '../src/contracts/trip-registry'

const bundle = JSON.parse(readFileSync(resolve(process.cwd(), 'public/trips/wanhua-2026/public-bundle.json'), 'utf8'))
const registry = JSON.parse(readFileSync(resolve(process.cwd(), 'public/trip-registry.json'), 'utf8'))

describe('萬華 2026 公開旅程', () => {
  it('is compatible with the public bundle contract', () => {
    expect(parseBundle(bundle)).toEqual({ ok: true, value: bundle })
    expect(bundle.date_range).toEqual({ start_date: '2026-09-30', end_date: '2026-10-02' })
    expect(bundle.traveler_profile).toMatchObject({ adults: 1, children_count: 0 })
    expect(bundle.presentation?.available_sections).toEqual(['overview', 'today'])
  })

  it('is a public preview with honest lodging and ticket data', () => {
    const entry = registry.find((item: { slug?: string }) => item.slug === 'wanhua-2026')
    expect(isCatalogEntry(entry)).toBe(true)
    expect(entry).toMatchObject({ status: 'preview', readiness: 'incomplete', duration_days: 3 })
    expect(bundle.budget.categories['core-tickets']).toEqual({ amount: 0, currency: 'TWD' })
    expect(bundle.budget.categories.metro).toEqual({ amount: 60, currency: 'TWD' })
    expect(bundle.places.find((place: { id?: string }) => place.id === 'hotel-riverview')?.opening_hours_note).toContain('未宣稱已完成訂房')
  })

  it('keeps leisure activities after 18:00', () => {
    const firstDay = bundle.days[0]
    const secondDay = bundle.days[1]
    const leisureItems = [firstDay, secondDay].flatMap((day: { items: Array<{ kind: string, start_at: string }> }) => day.items)
      .filter((item: { kind: string }) => item.kind === 'visit' || item.kind === 'meal')
    expect(leisureItems).not.toHaveLength(0)
    expect(leisureItems.every((item: { start_at: string }) => item.start_at.slice(11, 16) >= '18:00')).toBe(true)
    expect(firstDay.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'd1-hotel-river-view-check', start_at: '2026-09-30T18:00:00+08:00' }),
      expect.objectContaining({ id: 'd1-huazhong-riverside-night-view', start_at: '2026-09-30T18:50:00+08:00' }),
    ]))
    expect(secondDay.items[0]).toMatchObject({ id: 'd2-hotel-to-huaxi', start_at: '2026-10-01T18:00:00+08:00' })
    expect(bundle.days.at(-1).items.at(-1)).toMatchObject({ id: 'd3-ximen-to-qizhang', place_id: 'qizhang-station' })
  })

  it('shows five nearby Agoda candidates as rejected when none passes the river-view gate', () => {
    expect(bundle.hotel_candidates).toHaveLength(5)
    expect(bundle.hotel_candidates[0]).toMatchObject({
      place_id: 'hotel-riverview',
      selected_candidate: false,
      price_status: 'warning',
    })
    expect(bundle.hotel_candidates[0].room_type).toContain('河景')
    expect(bundle.hotel_candidates[0].price_note).toContain('NT$6,000')
    expect(bundle.hotel_candidates[0].distance_notes).toEqual(expect.arrayContaining([
      expect.stringContaining('華中河濱公園'),
      expect.stringContaining('華西街觀光夜市'),
      expect.stringContaining('西門紅樓'),
      expect.stringContaining('龍山寺'),
    ]))
    expect(bundle.hotel_candidates.map((candidate: { place_id: string }) => candidate.place_id)).toEqual([
      'hotel-riverview',
      'hotel-suz-catorze',
      'hotel-new-riverview-suites',
      'hotel-i-play-inn',
      'hotel-citizenm-north-gate',
    ])
    expect(bundle.hotel_candidates.every((candidate: { price_status?: string }) => candidate.price_status === 'warning')).toBe(true)
    expect(bundle.hotel_candidates.every((candidate: { price_note?: string }) => candidate.price_note?.includes('已淘汰'))).toBe(true)
    expect(bundle.hotel_candidates.every((candidate: { search_url?: string }) => candidate.search_url?.includes('agoda.com'))).toBe(true)
    expect(bundle.hotel_candidates.filter((candidate: { itinerary_compatible?: boolean }) => candidate.itinerary_compatible !== false)).toHaveLength(5)
  })

  it('keeps nearby non-river lodging leads out of the river-view candidate list', () => {
    expect(bundle.hotel_candidates.map((candidate: { place_id: string }) => candidate.place_id)).not.toEqual(expect.arrayContaining([
      'hotel-wholesome',
      'hotel-caesar-metro',
      'hotel-manka',
      'hotel-longshan-business',
    ]))
    const places = new Map(bundle.places.map((place: { id: string, name: string, official_url?: string }) => [place.id, place]))
    expect(places.get('hotel-wholesome')).toMatchObject({ name: '禾順行旅 Wholesome Hotel', official_url: 'https://www.wholesomehotel.com/' })
    expect(places.get('hotel-caesar-metro')).toMatchObject({ name: '台北凱達大飯店 Caesar Metro Taipei', official_url: 'https://www.caesarmetro.com/contact/' })
  })
})
