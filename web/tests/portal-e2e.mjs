/* global document, getComputedStyle */

import { chromium } from 'playwright'
import { copyFileSync, cpSync, mkdirSync, readdirSync } from 'node:fs'
import { startPreviewServer } from './preview-server.mjs'

for (const slug of ['awaji-2026', 'kansai-preview-2025', 'japan-archive-example', 'japan-blocked-example']) {
  mkdirSync(`dist/trips/${slug}`, { recursive: true })
  copyFileSync('dist/index.html', `dist/trips/${slug}/index.html`)
  if (slug === 'japan-archive-example' || slug === 'japan-blocked-example') {
    copyFileSync('dist/trips/kansai-preview-2025/public-bundle.json', `dist/trips/${slug}/public-bundle.json`)
  }
  for (const item of readdirSync('dist')) {
    if (item === 'index.html' || item === 'trips') continue
    cpSync(`dist/${item}`, `dist/trips/${slug}/${item}`, { recursive: true })
  }
}

const baseUrl = 'http://127.0.0.1:4174/'
const { stop, waitForServer } = startPreviewServer({
  args: ['--host', '127.0.0.1', '--port', '4174'],
  baseUrl,
  attempts: 30,
})

async function assertPortalLayout(page, width) {
  const layout = await page.evaluate(() => {
    const bounds = (element) => {
      const rectangle = element.getBoundingClientRect()
      return {
        left: rectangle.left,
        right: rectangle.right,
        top: rectangle.top,
        bottom: rectangle.bottom,
      }
    }
    const surfaces = [...document.querySelectorAll('.portal-hero, .search-shell, .trip-card')]
      .filter((element) => {
        const style = getComputedStyle(element)
        const rectangle = element.getBoundingClientRect()
        return style.visibility !== 'hidden' && style.display !== 'none' && rectangle.width > 0 && rectangle.height > 0
      })
    const rectangles = surfaces.map(bounds)
    const collisions = []
    for (let first = 0; first < rectangles.length; first += 1) {
      for (let second = first + 1; second < rectangles.length; second += 1) {
        const a = rectangles[first]
        const b = rectangles[second]
        if (a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1) {
          collisions.push([first, second])
        }
      }
    }
    const cardPadding = [...document.querySelectorAll('.trip-card-body')].map((element) => {
      const style = getComputedStyle(element)
      return [Number.parseFloat(style.paddingLeft), Number.parseFloat(style.paddingRight)]
    })
    const orderedCards = [...document.querySelectorAll('.trip-card')]
      .map((element) => element.getBoundingClientRect())
      .sort((a, b) => a.top - b.top)
    const cardGaps = orderedCards.slice(1).map((card, index) => card.top - orderedCards[index].bottom)
    return {
      documentWidth: document.documentElement.scrollWidth,
      surfaceLeft: Math.min(...rectangles.map((rectangle) => rectangle.left)),
      surfaceRight: Math.max(...rectangles.map((rectangle) => rectangle.right)),
      cardPadding,
      cardGaps,
      collisions,
    }
  })
  if (layout.documentWidth > width + 1) throw new Error(`${width}px root catalog overflowed to ${layout.documentWidth}px`)
  if (layout.surfaceLeft < 15 || layout.surfaceRight > width - 15) throw new Error(`${width}px root catalog gutter is too small: ${JSON.stringify(layout)}`)
  if (layout.cardPadding.some(([left, right]) => left < 16 || right < 16)) throw new Error(`${width}px root catalog card padding is too small: ${JSON.stringify(layout.cardPadding)}`)
  if (layout.cardGaps.some((gap) => gap < 14)) throw new Error(`${width}px root catalog card gap is too small: ${JSON.stringify(layout.cardGaps)}`)
  if (layout.collisions.length) throw new Error(`${width}px root catalog surfaces overlap: ${JSON.stringify(layout.collisions)}`)
}

const browser = await chromium.launch()
try {
  await waitForServer()
  for (const width of [375, 390, 430]) {
    const layoutPage = await browser.newPage({ viewport: { width, height: 844 } })
    layoutPage.setDefaultTimeout(10000)
    await layoutPage.goto(baseUrl, { waitUntil: 'domcontentloaded' })
    await layoutPage.locator('.trip-card').nth(1).waitFor({ state: 'visible' })
    if (await layoutPage.locator('.trip-card').count() !== 4) throw new Error(`${width}px root catalog did not render all recorded trips`)
    const portalText = await layoutPage.locator('body').innerText()
    if (/CANONICAL TRIP JOURNEYS|Kansai 2025|Archived example|Blocked example|family|self-drive|recorded-example|查看 trip/i.test(portalText)) throw new Error(`${width}px root catalog exposed internal English copy`)
    await assertPortalLayout(layoutPage, width)
    await layoutPage.close()
  }

  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  page.setDefaultTimeout(10000)
  page.setDefaultNavigationTimeout(10000)
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' })
  await page.locator('.trip-card').nth(1).waitFor({ state: 'visible' })
  if (await page.locator('.trip-card').count() !== 4) throw new Error('root catalog did not render all recorded trips')
  if (await page.locator('h1').filter({ hasText: 'AI Travel Planner' }).count() !== 1) throw new Error('root product identity missing')
  await page.locator('.trip-card').filter({ hasText: '淡路島五日行' }).getByRole('button', { name: '查看行程' }).click()
  await page.locator('.overview-day-grid').waitFor({ state: 'visible' })
  if (!page.url().includes('/trips/awaji-2026/')) throw new Error(`Awaji URL was not canonical: ${page.url()}`)
  if ((await page.title()).includes('Trip Planner')) throw new Error('trip metadata was not updated')
  await page.goto(`${baseUrl}trips/kansai-preview-2025/`, { waitUntil: 'domcontentloaded' })
  await page.locator('.overview-day-grid').waitFor({ state: 'visible' })
  if (await page.locator('.status-preview, .status-ready, .status-incomplete').count()) throw new Error('internal publication or readiness status leaked into the trip page')
  await page.goto(`${baseUrl}trips/japan-archive-example/`, { waitUntil: 'domcontentloaded' })
  await page.locator('.overview-day-grid').waitFor({ state: 'visible' })
  if (await page.locator('.status-archived').count()) throw new Error('internal archive status leaked into the trip page')
  await page.goto(`${baseUrl}trips/japan-blocked-example/`, { waitUntil: 'domcontentloaded' })
  await page.locator('.overview-day-grid').waitFor({ state: 'visible' })
  if (await page.locator('.status-blocked').count()) throw new Error('internal readiness status leaked into the trip page')
} finally {
  await browser.close()
  stop()
}
