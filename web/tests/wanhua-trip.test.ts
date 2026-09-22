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

  it('keeps leisure activities after 18:00 and leaves the daytime free', () => {
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

  it('makes river view and the all-in two-night ceiling an explicit lodging gate', () => {
    expect(bundle.hotel_candidates).toHaveLength(5)
    expect(bundle.hotel_candidates[0]).toMatchObject({
      place_id: 'hotel-riverview',
      selected_candidate: false,
      price_status: 'unverified',
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
      'hotel-papa-whale',
      'hotel-wonstar',
      'hotel-monka',
      'hotel-hz',
    ])
    expect(bundle.hotel_candidates.every((candidate: { price_note?: string }) => candidate.price_note?.includes('一房兩人資料') || candidate.price_note?.includes('一成人') || candidate.price_note?.includes('1 成人'))).toBe(true)
    expect(bundle.hotel_candidates.every((candidate: { search_url?: string }) => Boolean(candidate.search_url))).toBe(true)
  })
})
