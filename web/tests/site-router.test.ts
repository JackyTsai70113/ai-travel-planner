import { describe, expect, it } from 'vitest'
import { parseSiteRoute, siteRootFromPageUrl, tripUrl } from '../src/app/site-router'
import { sitePageUrl, siteRootUrl } from '../src/app/site-links'

describe('site routing', () => {
  it('recognizes the root portal and recorded trip paths', () => {
    expect(parseSiteRoute('/ai-travel-planner/')).toEqual({ kind: 'home' })
    expect(parseSiteRoute('/ai-travel-planner/trips/kansai-preview-2025/')).toEqual({ kind: 'trip', slug: 'kansai-preview-2025' })
    expect(parseSiteRoute('/ai-travel-planner/trips/')).toEqual({ kind: 'not-found' })
    expect(parseSiteRoute('/ai-travel-planner/unknown/')).toEqual({ kind: 'not-found' })
    expect(parseSiteRoute('/ai-travel-planner/terms.html')).toEqual({ kind: 'terms' })
    expect(parseSiteRoute('/ai-travel-planner/privacy.html')).toEqual({ kind: 'privacy' })
  })

  it('preserves a project Pages base path when building trip links', () => {
    const current = 'https://example.test/ai-travel-planner/'
    expect(siteRootUrl(current).toString()).toBe(current)
    expect(tripUrl('awaji-2026', current)).toBe('https://example.test/ai-travel-planner/trips/awaji-2026/')
    expect(siteRootFromPageUrl('https://example.test/ai-travel-planner/trips/awaji-2026/').toString()).toBe(current)
    expect(sitePageUrl('terms', 'https://example.test/ai-travel-planner/trips/awaji-2026/')).toBe('https://example.test/ai-travel-planner/terms.html')
    expect(sitePageUrl('privacy', current)).toBe('https://example.test/ai-travel-planner/privacy.html')
    expect(siteRootUrl('https://example.test/ai-travel-planner/terms.html').toString()).toBe(current)
  })
})
