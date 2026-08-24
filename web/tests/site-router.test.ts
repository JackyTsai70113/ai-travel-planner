import { describe, expect, it } from 'vitest'
import { parseSiteRoute, siteRootUrl, tripUrl } from '../src/app/site-router'

describe('site routing', () => {
  it('recognizes the root portal and recorded trip paths', () => {
    expect(parseSiteRoute('/ai-travel-planner/')).toEqual({ kind: 'home' })
    expect(parseSiteRoute('/ai-travel-planner/trips/kansai-preview-2025/')).toEqual({ kind: 'trip', slug: 'kansai-preview-2025' })
  })

  it('preserves a project Pages base path when building trip links', () => {
    const current = 'https://example.test/ai-travel-planner/'
    expect(siteRootUrl(current).toString()).toBe(current)
    expect(tripUrl('awaji-2026', current)).toBe('https://example.test/ai-travel-planner/trips/awaji-2026/')
  })
})
