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

  it('uses seven-zhang as a continuous public-transit start and return, without synthetic hotel loops', () => {
    const firstDay = bundle.days[0]
    const finalDay = bundle.days.at(-1)
    expect(firstDay.items[0]).toMatchObject({ id: 'd1-qizhang-to-ximen', place_id: 'ximen-station' })
    const stopSequence = firstDay.items
      .map((item: { place_id: string }) => item.place_id)
      .filter((placeId: string, index: number, all: string[]) => index === 0 || placeId !== all[index - 1])
    expect(stopSequence).toEqual(['ximen-station', 'red-house', 'ximen-pedestrian-area', 'hotel-riverview', 'huazhong-riverside-park', 'hotel-riverview'])
    expect(finalDay.items.at(-1)).toMatchObject({ id: 'd3-ximen-to-qizhang', place_id: 'qizhang-station' })
    expect(bundle.transport_legs.find((leg: { id: string }) => leg.id === 'qizhang-to-ximen')).toMatchObject({
      from_place: 'qizhang-station', to_place: 'ximen-station', source_url: 'https://web.metro.taipei/pages2026/WebStation/035/8',
    })
  })

  it('shows five researched lodging candidates without claiming a booking or a solo final price', () => {
    expect(bundle.hotel_candidates).toHaveLength(5)
    expect(bundle.hotel_candidates[0]).toMatchObject({
      place_id: 'hotel-riverview',
      selected_candidate: true,
      price_status: 'unverified',
    })
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
