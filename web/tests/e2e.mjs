import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { copyFileSync, cpSync, mkdirSync, readdirSync } from 'node:fs'

copyFileSync(
  new URL('../public/trips/awaji-2026/public-bundle.json', import.meta.url),
  new URL('../dist/public-bundle.json', import.meta.url),
)
mkdirSync(new URL('../dist/trips/awaji-2026/', import.meta.url), { recursive: true })
copyFileSync(
  new URL('../public/trips/awaji-2026/public-bundle.json', import.meta.url),
  new URL('../dist/trips/awaji-2026/public-bundle.json', import.meta.url),
)
for (const item of readdirSync(new URL('../dist/', import.meta.url))) {
  if (item === 'trips') continue
  cpSync(new URL(`../dist/${item}`, import.meta.url), new URL(`../dist/trips/awaji-2026/${item}`, import.meta.url), { recursive: true })
}

const deploymentPath = '/ai-travel-planner/'
const baseUrl = `http://127.0.0.1:4173${deploymentPath}trips/awaji-2026/`
const dates = ['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31']
const server = spawn('npm', ['run', 'preview', '--', '--base', deploymentPath, '--host', '127.0.0.1', '--port', '4173'], { stdio: 'inherit' })
server.unref()
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
  const section = route.split('/')[0]
  const readySelectors = {
    overview: '.trip-overview-shell',
    today: '.itinerary-workspace',
    lodging: '.lodging-workspace',
    packing: '.packing-workspace',
    sources: '[aria-label="資料來源"]',
  }
  const readySelector = readySelectors[section]
  if (readySelector) await page.locator(readySelector).waitFor({ state: 'visible' })
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

function contrastRatio(foreground, background, label) {
  const parseRgb = (value) => {
    const channels = value.match(/[\d.]+/g)?.map(Number)
    if (!channels || channels.length < 3) throw new Error(`${label} has unsupported color: ${value}`)
    return channels.slice(0, 3)
  }
  const luminance = (value) => {
    const channels = parseRgb(value).map((channel) => {
      const normalized = channel / 255
      return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
    })
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
  }
  const foregroundLuminance = luminance(foreground)
  const backgroundLuminance = luminance(background)
  return (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) / (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
}

function assertMinimumContrast(colors, minimum, label) {
  const ratio = contrastRatio(colors.foreground, colors.background, label)
  if (ratio < minimum) {
    throw new Error(`${label} contrast is ${ratio.toFixed(2)}:1 (${colors.foreground} on ${colors.background}); expected at least ${minimum}:1`)
  }
}

async function assertStyleContrast(page, foregroundSelector, foregroundProperty, backgroundSelector, backgroundProperty, minimum, label) {
  const colors = await page.evaluate(({ foregroundSelector, foregroundProperty, backgroundSelector, backgroundProperty }) => {
    const foreground = document.querySelector(foregroundSelector)
    const background = document.querySelector(backgroundSelector)
    if (!foreground || !background) return null
    return {
      foreground: getComputedStyle(foreground)[foregroundProperty],
      background: getComputedStyle(background)[backgroundProperty],
    }
  }, { foregroundSelector, foregroundProperty, backgroundSelector, backgroundProperty })
  if (!colors) throw new Error(`${label} contrast elements were not rendered`)
  assertMinimumContrast(colors, minimum, label)
}

async function assertTextContrast(page, selector, minimum, label) {
  const colors = await page.locator(selector).first().evaluate((element) => {
    let background = element
    while (background.parentElement && getComputedStyle(background).backgroundColor === 'rgba(0, 0, 0, 0)') {
      background = background.parentElement
    }
    return {
      foreground: getComputedStyle(element).color,
      background: getComputedStyle(background).backgroundColor,
    }
  })
  assertMinimumContrast(colors, minimum, label)
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch()

  const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const mobile = await mobileContext.newPage()
  mobile.setDefaultTimeout(10000)

  await openRoute(mobile, 'overview')
  if (await mobile.locator('.mobile-bottom-nav').count()) throw new Error('mobile bottom navigation must not be rendered')
  const menuButton = mobile.getByRole('button', { name: '展開導覽選單' })
  await assertTouchTargets(mobile, '.menu-button', 'hamburger menu')
  await assertStyleContrast(mobile, '.menu-button', 'color', '.menu-button', 'backgroundColor', 4.5, 'hamburger icon')
  await assertStyleContrast(mobile, '.menu-button', 'borderTopColor', '.mobile-topbar', 'backgroundColor', 3, 'hamburger boundary')
  if (await menuButton.getAttribute('aria-expanded') !== 'false') throw new Error('hamburger menu did not expose its collapsed state')
  await menuButton.click()
  const drawer = mobile.locator('#mobile-navigation-drawer')
  await drawer.waitFor({ state: 'visible' })
  if (await menuButton.getAttribute('aria-expanded') !== 'true') throw new Error('hamburger menu did not expose its expanded state')
  if (!(await drawer.locator('[aria-current="page"]').textContent())?.includes('目前')) throw new Error('drawer did not label the current section')
  await assertTouchTargets(mobile, '.drawer-nav-item', 'drawer navigation')
  await mobile.keyboard.press('Escape')
  await drawer.waitFor({ state: 'detached' })
  if (await menuButton.getAttribute('aria-expanded') !== 'false') throw new Error('hamburger menu did not expose its collapsed state after Escape')
  if (!(await menuButton.evaluate((element) => element === document.activeElement))) throw new Error('focus did not return to the hamburger menu after closing the drawer')
  await assertTextContrast(mobile, '.overview-day-copy > p', 4.5, 'overview secondary text')
  await assertTextContrast(mobile, '.overview-footer span', 4.5, 'overview footer text')

  await openRoute(mobile, 'sources')
  await mobile.locator('h1, h2').filter({ hasText: '資料來源' }).waitFor({ state: 'attached' })
  await openRoute(mobile, 'today')
  if (!mobile.url().includes('#/today')) throw new Error(`today route was not preserved: ${mobile.url()}`)
  if (await mobile.locator('.day-tab').count() !== 5) throw new Error('five itinerary days were not rendered')

  for (const route of ['overview', 'today', 'lodging', 'packing']) {
    await openRoute(mobile, route)
    await assertNoHorizontalOverflow(mobile, `390px ${route}`)
  }

  await openRoute(mobile, 'today/2026-08-29')
  await assertTextContrast(mobile, '.timeline-time span', 4.5, 'timeline secondary time')
  await assertTextContrast(mobile, '.timeline-detail', 4.5, 'timeline detail')
  await assertTouchTargets(mobile, '.day-tab', 'day tab')
  await assertTouchTargets(mobile, '.print-button', 'print')
  await assertTouchTargets(mobile, '.quick-mode button', 'quick mode')
  await assertTouchTargets(mobile, '.timeline-actions a, .timeline-actions button', 'timeline action')
  await mobile.locator('#itinerary-search').fill('淡路')
  await mobile.locator('.search-results button').first().waitFor()
  await assertTouchTargets(mobile, '.search-results button', 'search result')

  await openRoute(mobile, 'today/2026-08-29')

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
  await assertTextContrast(mobile, '.stay-note', 4.5, 'lodging note')

  await openRoute(mobile, 'packing')
  if (await mobile.getByRole('checkbox').count() !== 30) throw new Error('spreadsheet checklist did not render 30 items')
  await mobile.getByText('預約 Ocean Terrace', { exact: true }).waitFor()
  await assertTextContrast(mobile, '.checklist-copy p', 4.5, 'packing detail')
  await mobileContext.close()

  const desktopContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const desktop = await desktopContext.newPage()
  desktop.setDefaultTimeout(10000)
  for (const route of ['overview', 'today']) {
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
    await openRoute(routePage, `today/${date}`)
    const riskCard = routePage.locator('.day-answer-grid > div').filter({ hasText: '主要風險' })
    await riskCard.waitFor({ state: 'visible' })
    const riskText = (await riskCard.locator('strong').textContent())?.trim()
    if (!riskText) throw new Error(`${date} did not render a primary risk summary`)
    if (date === '2026-08-27') {
      const fixedCard = routePage.locator('.day-answer-grid > div').filter({ hasText: '固定時間' })
      if (!(await fixedCard.textContent())?.includes('10:30')) throw new Error('Day 1 hero did not preserve the JX834 fixed arrival time')
    }
    if (date === '2026-08-31') {
      const fixedCard = routePage.locator('.day-answer-grid > div').filter({ hasText: '固定時間' })
      const fixedText = await fixedCard.textContent()
      if (!fixedText?.includes('12:45') || !fixedText.includes('神戶機場 第二航廈')) throw new Error('Day 5 hero did not preserve the JX1835 departure time and origin')
      const flightMapHref = await routePage.locator('#item-day5-departure-flight').getByRole('link', { name: '導航地圖' }).getAttribute('href')
      const flightMapQuery = flightMapHref ? new URL(flightMapHref).searchParams.get('query') : null
      const normalizedFlightMapQuery = flightMapQuery?.toLowerCase() || ''
      if ((!normalizedFlightMapQuery.includes('kobe') && !flightMapQuery?.includes('神戸空港')) || flightMapQuery?.includes('桃園')) throw new Error(`Day 5 flight navigation target is incorrect: ${flightMapQuery}`)
    }

    await openRoute(routePage, `today/${date}`)
    const legCards = routePage.locator('.timeline-entry').filter({ hasText: '逐段交通' })
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
