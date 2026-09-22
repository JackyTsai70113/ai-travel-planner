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
  })

  it('is a public preview with honest lodging and ticket data', () => {
    const entry = registry.find((item: { slug?: string }) => item.slug === 'wanhua-2026')
    expect(isCatalogEntry(entry)).toBe(true)
    expect(entry).toMatchObject({ status: 'preview', readiness: 'incomplete', duration_days: 3 })
    expect(bundle.budget.categories['core-tickets']).toEqual({ amount: 0, currency: 'TWD' })
    expect(bundle.places.find((place: { id?: string }) => place.id === 'westgate-hotel')?.opening_hours_note).toContain('未宣稱已完成訂房')
  })
})
