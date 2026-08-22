import { chromium } from 'playwright'
import { spawn } from 'node:child_process'

const baseUrl = 'http://127.0.0.1:4173/'
const dates = ['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31']
const server = spawn('npm', ['run', 'preview', '--', '--host', '127.0.0.1', '--port', '4173'], { stdio: 'inherit' })
const stop = () => server.kill('SIGTERM')
process.on('exit', stop)

async function waitForServer() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const response = await fetch(baseUrl)
      if (response.ok) return
    } catch {
      // Preview server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  throw new Error('preview server did not start')
}

async function openRoute(page, route) {
  await page.goto(`${baseUrl}#/${route}`, { waitUntil: 'domcontentloaded' })
  await page.locator('.app-shell').waitFor({ state: 'attached' })
  await page.locator('#trip-main').waitFor({ state: 'attached' })
}

async function assertNoHorizontalOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  if (dimensions.scrollWidth > dimensions.clientWidth) {
    throw new Error(`${label} horizontal overflow: ${dimensions.scrollWidth} > ${dimensions.clientWidth}`)
  }
}

async function assertTouchTargets(page, selector, label) {
  const targets = page.locator(selector)
  const count = await targets.count()
  if (count === 0) throw new Error(`${label} touch targets were not rendered`)
  for (let index = 0; index < count; index += 1) {
    const target = targets.nth(index)
    if (!(await target.isVisible())) continue
    const box = await target.boundingBox()
    if (!box || box.width < 44 || box.height < 44) {
      throw new Error(`${label} touch target ${index + 1} is ${box?.width ?? 0}×${box?.height ?? 0}px; expected at least 44×44px`)
    }
  }
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch()

  const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const mobile = await mobileContext.newPage()
  mobile.setDefaultTimeout(10000)

  await openRoute(mobile, 'sources')
  await mobile.locator('h1, h2').filter({ hasText: '資料來源' }).waitFor({ state: 'attached' })
  await openRoute(mobile, 'today')
  if (!mobile.url().includes('#/today')) throw new Error(`today route was not preserved: ${mobile.url()}`)
  if (await mobile.locator('.day-tab').count() !== 5) throw new Error('five itinerary days were not rendered')

  for (const route of ['overview', 'today', 'map', 'lodging', 'packing']) {
    await openRoute(mobile, route)
    await assertNoHorizontalOverflow(mobile, `390px ${route}`)
  }

  await openRoute(mobile, 'today/2026-08-29')
  await assertTouchTargets(mobile, '.day-tab', 'day tab')
  await assertTouchTargets(mobile, '.print-button', 'print')
  await assertTouchTargets(mobile, '.quick-mode button', 'quick mode')
  await assertTouchTargets(mobile, '.plan-tabs button', 'plan')
  await assertTouchTargets(mobile, '.timeline-actions a, .timeline-actions button', 'timeline action')
  await mobile.locator('#itinerary-search').fill('淡路')
  await mobile.locator('.search-results button').first().waitFor()
  await assertTouchTargets(mobile, '.search-results button', 'search result')

  await openRoute(mobile, 'map/2026-08-27')
  await assertTouchTargets(mobile, '.handbook-day-tabs button', 'map day tab')

  await openRoute(mobile, 'lodging')
  const longJapaneseName = mobile.locator('.lodging-card-main h2').filter({ hasText: 'ザ ロイヤルパーク キャンバス 神戸三宮' })
  await longJapaneseName.waitFor()
  const wrap = await longJapaneseName.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    overflowWrap: getComputedStyle(element).overflowWrap,
  }))
  if (wrap.scrollWidth > wrap.clientWidth || wrap.overflowWrap !== 'anywhere') {
    throw new Error(`long Japanese lodging name did not wrap safely: ${JSON.stringify(wrap)}`)
  }

  await openRoute(mobile, 'packing')
  if (await mobile.getByRole('checkbox').count() !== 30) throw new Error('spreadsheet checklist did not render 30 items')
  await mobile.getByText('預約 Ocean Terrace', { exact: true }).waitFor()
  await mobileContext.close()

  const desktopContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const desktop = await desktopContext.newPage()
  desktop.setDefaultTimeout(10000)
  for (const route of ['overview', 'today', 'map']) {
    await openRoute(desktop, route)
    await desktop.locator('.trip-sidebar').waitFor({ state: 'visible' })
    await desktop.locator('.app-main').waitFor({ state: 'visible' })
    await assertNoHorizontalOverflow(desktop, `1440px ${route}`)
  }
  await desktopContext.close()

  const routeContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const routePage = await routeContext.newPage()
  routePage.setDefaultTimeout(10000)
  for (const date of dates) {
    await openRoute(routePage, `map/${date}`)
    const legCards = routePage.locator('[data-testid^="transport-leg-"]')
    await legCards.first().waitFor({ state: 'visible' })
    const legCount = await legCards.count()
    if (legCount < 1) throw new Error(`${date} did not render any transport leg`)
    if (await routePage.getByText('尚無逐段資料', { exact: true }).count()) {
      throw new Error(`${date} rendered the empty route state`)
    }
  }
  await routeContext.close()
} finally {
  await browser?.close()
  stop()
}
