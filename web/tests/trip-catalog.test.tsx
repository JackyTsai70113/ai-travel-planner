import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TripCatalogEntry, TripRegistrySections } from '../src/contracts/trip-registry'
import { buildCatalogSections } from '../src/contracts/trip-registry'
import HomePage from '../src/pages/HomePage'

const entry: TripCatalogEntry = {
  slug: 'awaji-2026',
  canonical_url: 'trips/awaji-2026',
  title: '2026 淡路島五日行',
  short_title: '淡路島五日行',
  destination_regions: ['淡路島'],
  date_range: { start_date: '2026-08-27', end_date: '2026-08-31' },
  duration_days: 5,
  travelers_summary: '6 大 1 小',
  theme_id: 'setouchi-awaji',
  status: 'published',
  readiness: 'incomplete',
  last_generated: '2026-08-10',
  last_verified: '2026-08-15',
  tags: ['family'],
  cover_media: { kind: 'gradient', gradient: 'linear-gradient(#123, #456)' },
  hero_summary: '淡路島五日行程摘要',
  key_messages: [],
  critical_alert_count: 2,
}

const sections: TripRegistrySections = {
  featured: [entry],
  upcoming: [],
  archived: [],
  preview: [],
}

describe('旅行目錄公開狀態', () => {
  afterEach(() => cleanup())

  it('將已結束的公開行程移至封存，當日結束的行程仍留在當前分類', () => {
    const currentEntry = { ...entry, slug: 'current-trip', date_range: { start_date: '2026-10-05', end_date: '2026-10-08' } }
    const futureEntry = { ...entry, slug: 'future-trip', date_range: { start_date: '2026-11-01', end_date: '2026-11-05' } }
    const result = buildCatalogSections([entry, currentEntry, futureEntry], '2026-10-08')

    expect(result.featured.map((item) => item.slug)).toEqual(['current-trip'])
    expect(result.upcoming.map((item) => item.slug)).toEqual(['future-trip'])
    expect(result.archived).toEqual([{ ...entry, status: 'archived' }])
  })

  it('保留預覽和明確封存狀態', () => {
    const previewEntry = { ...entry, slug: 'preview-trip', status: 'preview' as const }
    const archivedEntry = { ...entry, slug: 'archived-trip', status: 'archived' as const }
    const result = buildCatalogSections([previewEntry, archivedEntry], '2026-10-08')

    expect(result.preview).toEqual([previewEntry])
    expect(result.archived).toEqual([archivedEntry])
  })

  it('將公開但未完成的行程標示為公開預覽，且說明發布狀態與完成度分開', () => {
    render(<HomePage catalog={[entry]} sections={sections} setRoute={vi.fn()} searchPlaceholder="搜尋旅行" />)

    expect(screen.getByText('公開預覽')).toBeInTheDocument()
    expect(screen.getByText('頁面公開狀態與行程完成度分開呈現；公開預覽不代表行程已確認。')).toBeInTheDocument()
    expect(screen.queryByText('已發布')).not.toBeInTheDocument()
  })

  it('已完成並公開的行程仍標示為已發布', () => {
    const readyEntry = { ...entry, readiness: 'ready' as const }
    render(<HomePage catalog={[readyEntry]} sections={{ ...sections, featured: [readyEntry] }} setRoute={vi.fn()} searchPlaceholder="搜尋旅行" />)

    expect(screen.getByText('已發布')).toBeInTheDocument()
    expect(screen.queryByText('公開預覽')).not.toBeInTheDocument()
  })
})
