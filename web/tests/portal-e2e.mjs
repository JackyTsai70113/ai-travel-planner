/* global document, getComputedStyle */

import { chromium } from 'playwright'
import { copyFileSync, cpSync, mkdirSync, readdirSync } from 'node:fs'
import { startPreviewServer } from './preview-server.mjs'

for (const slug of ['wanhua-2026', 'awaji-2026', 'kansai-preview-2025', 'japan-archive-example', 'japan-blocked-example']) {
  mkdirSync(`dist/trips/${slug}`, { recursive: true })
  copyFileSync('dist/index.html', `dist/trips/${slug}/index.html`)
  for (const item of readdirSync('dist')) {
    if (item === 'index.html' || item === 'trips') continue
    cpSync(`dist/${item}`, `dist/trips/${slug}/${item}`, { recursive: true })
  }
  const sourceSlug = slug === 'japan-archive-example' || slug === 'japan-blocked-example' ? 'kansai-preview-2025' : slug
  copyFileSync(`public/trips/${sourceSlug}/public-bundle.json`, `dist/trips/${slug}/public-bundle.json`)
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
    if (await layoutPage.locator('.trip-card').count() !== 5) throw new Error(`${width}px root catalog did not render all visible trips`)
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
  if (await page.locator('.trip-card').count() !== 5) throw new Error('root catalog did not render all visible trips')
  if (await page.locator('h1').filter({ hasText: 'AI Travel Planner' }).count() !== 1) throw new Error('root product identity missing')
  await Promise.all([
    page.waitForURL('**/trips/wanhua-2026/'),
    page.locator('.trip-card').filter({ hasText: '萬華三天兩夜一人行' }).getByRole('button', { name: '查看行程' }).click(),
  ])
  await page.locator('.overview-day-grid').waitFor({ state: 'visible' })
  if (!page.url().includes('/trips/wanhua-2026/')) throw new Error(`Wanhua URL was not canonical: ${page.url()}`)
  const wanhuaOverviewText = await page.locator('body').innerText()
  if (!wanhuaOverviewText.includes('18:00 後：河景夜色與華中河濱備選')) throw new Error('Wanhua night-only day one summary did not render')
  if (!wanhuaOverviewText.includes('河景房必須符合：兩晚含稅不超過 NT$6,000')) throw new Error('Wanhua river-view lodging gate did not render')
  const wanhuaErrors = []
  page.on('pageerror', (error) => wanhuaErrors.push(error.message))
  const wanhuaRoutes = [
    ['today/2026-09-30', '.itinerary-workspace'],
    ['today/2026-10-01', '.itinerary-workspace'],
    ['today/2026-10-02', '.itinerary-workspace'],
  ]
  for (const [route, selector] of wanhuaRoutes) {
    await page.goto(`${baseUrl}trips/wanhua-2026/#/${route}`, { waitUntil: 'domcontentloaded' })
    await page.locator(selector).waitFor({ state: 'visible' })
    if (route === 'today/2026-09-30') {
      const dayOneText = await page.locator('.itinerary-workspace').innerText()
      if (!dayOneText.includes('華中河濱公園') || !dayOneText.includes('照明正常且現場有人流')) throw new Error('Wanhua riverside night view or safety condition did not render')
    }
    if (wanhuaErrors.length) throw new Error(`Wanhua ${route} raised a runtime error: ${wanhuaErrors.join(' | ')}`)
  }

  const interactionPage = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  interactionPage.setDefaultTimeout(10000)
  const interactionErrors = []
  interactionPage.on('pageerror', (error) => interactionErrors.push(error.message))
  const assertNoInteractionErrors = (step) => {
    if (interactionErrors.length) throw new Error(`Wanhua interaction ${step} raised a runtime error: ${interactionErrors.join(' | ')}`)
  }
  await interactionPage.goto(`${baseUrl}trips/wanhua-2026/`, { waitUntil: 'domcontentloaded' })
  await interactionPage.locator('.overview-day-grid').waitFor({ state: 'visible' })

  const desktopNavigation = [
    ['旅行總覽', '#/overview', '.overview-day-grid'],
    ['每日行程', '#/today/2026-09-30', '.itinerary-workspace'],
  ]
  for (const [label, hash, selector] of desktopNavigation) {
    await interactionPage.locator('.trip-nav-item').filter({ hasText: label }).click()
    await interactionPage.waitForURL(`**/${hash}`)
    await interactionPage.locator(selector).waitFor({ state: 'visible' })
    assertNoInteractionErrors(`desktop navigation: ${label}`)
  }

  await interactionPage.locator('.sidebar-collapse').click()
  if (!(await interactionPage.locator('.trip-sidebar').evaluate((element) => element.classList.contains('is-collapsed')))) throw new Error('Wanhua sidebar did not collapse')
  await interactionPage.locator('.sidebar-collapse').click()
  if (await interactionPage.locator('.trip-sidebar').evaluate((element) => element.classList.contains('is-collapsed'))) throw new Error('Wanhua sidebar did not expand')

  await interactionPage.locator('.trip-nav-item').filter({ hasText: '每日行程' }).click()
  await interactionPage.locator('.itinerary-workspace').waitFor({ state: 'visible' })
  for (const [index, date] of ['2026-09-30', '2026-10-01', '2026-10-02'].entries()) {
    await interactionPage.locator(`.day-tab[aria-label^="第 ${index + 1} 天"]`).click()
    await interactionPage.waitForURL(`**/#/today/${date}`)
    await interactionPage.locator('.day-kicker').filter({ hasText: date }).waitFor({ state: 'visible' })
    assertNoInteractionErrors(`day tab ${index + 1}`)
  }
  if (await interactionPage.locator('.daily-route-map, .day-guide-notice, .day-alternatives, .place-guide-notice').count()) throw new Error('Wanhua itinerary showed empty or duplicate research panels')
  await interactionPage.locator('.print-button').click()
  if (!(await interactionPage.locator('.itinerary-workspace').evaluate((element) => element.classList.contains('print-itinerary')))) throw new Error('Wanhua print view did not open')
  await interactionPage.getByRole('button', { name: '返回行程' }).click()
  if (await interactionPage.locator('.itinerary-workspace').evaluate((element) => element.classList.contains('print-itinerary'))) throw new Error('Wanhua print view did not close')
  for (const label of ['現在', '下一站', '全部']) {
    await interactionPage.getByRole('button', { name: label, exact: true }).click()
    if ((await interactionPage.getByRole('button', { name: label, exact: true }).getAttribute('aria-pressed')) !== 'true') throw new Error(`Wanhua quick filter ${label} was not selected`)
    assertNoInteractionErrors(`quick filter ${label}`)
  }

  const wanhuaText = await interactionPage.locator('body').innerText()
  if (/日文|日圓|護照|幼兒|船班|JX\d|自駕/.test(wanhuaText)) throw new Error('Wanhua exposed Japan-template content')
  await interactionPage.close()

  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } })
  mobilePage.setDefaultTimeout(10000)
  const mobileErrors = []
  mobilePage.on('pageerror', (error) => mobileErrors.push(error.message))
  await mobilePage.goto(`${baseUrl}trips/wanhua-2026/`, { waitUntil: 'domcontentloaded' })
  const mobileNavigation = [
    ['旅行總覽', '.overview-day-grid'],
    ['每日行程', '.itinerary-workspace'],
  ]
  for (const [label, selector] of mobileNavigation) {
    await mobilePage.getByRole('button', { name: '展開導覽選單' }).click()
    await mobilePage.locator('.mobile-drawer').waitFor({ state: 'visible' })
    await mobilePage.locator('.drawer-nav-item').filter({ hasText: label }).click()
    await mobilePage.locator(selector).waitFor({ state: 'visible' })
    if (await mobilePage.locator('.mobile-drawer').count()) throw new Error(`Wanhua mobile drawer did not close after ${label}`)
  }
  await mobilePage.getByRole('button', { name: '展開導覽選單' }).click()
  await mobilePage.getByRole('button', { name: '關閉導覽' }).click()
  if (await mobilePage.locator('.mobile-drawer').count()) throw new Error('Wanhua mobile drawer close button did not work')
  if (mobileErrors.length) throw new Error(`Wanhua mobile interactions raised a runtime error: ${mobileErrors.join(' | ')}`)
  await mobilePage.close()
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' })
  await page.goto(`${baseUrl}trips/awaji-2026/`, { waitUntil: 'domcontentloaded' })
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
