import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { copyFileSync, cpSync, mkdirSync, readdirSync } from 'node:fs'

copyFileSync(new URL('../public/trips/awaji-2026/public-bundle.json', import.meta.url), new URL('../dist/public-bundle.json', import.meta.url))
mkdirSync(new URL('../dist/trips/awaji-2026/', import.meta.url), { recursive: true })
copyFileSync(new URL('../public/trips/awaji-2026/public-bundle.json', import.meta.url), new URL('../dist/trips/awaji-2026/public-bundle.json', import.meta.url))
for (const item of readdirSync(new URL('../dist/', import.meta.url))) {
  if (item === 'trips') continue
  cpSync(new URL(`../dist/${item}`, import.meta.url), new URL(`../dist/trips/awaji-2026/${item}`, import.meta.url), { recursive: true })
}

const deploymentPath = '/ai-travel-planner/'
const baseUrl = `http://127.0.0.1:4173${deploymentPath}trips/awaji-2026/`
const dates = ['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31']
const forbidden = /待補|未提供|狀態正常|規劃估計|硬截止|硬離場|Sheet 指定|家庭／無障礙|聯絡[／/]參考|Canonical Trip|資料快照|熱中症|UTC|資料來源|旅行資訊/
const server = spawn('npm', ['run', 'preview', '--', '--base', deploymentPath, '--host', '127.0.0.1', '--port', '4173'], { stdio: 'inherit' })
server.unref()
const stop = () => server.kill('SIGTERM')
process.on('exit', stop)

async function waitForServer() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
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

async function openRoute(page, route, readySelector) {
  await page.goto(`${baseUrl}#/${route}`, { waitUntil: 'domcontentloaded' })
  await page.locator(readySelector).waitFor({ state: 'visible' })
}

async function assertNoHorizontalOverflow(page, label) {
  const size = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }))
  if (size.scroll > size.client) throw new Error(`${label} horizontal overflow: ${size.scroll} > ${size.client}`)
}

async function assertNoForbiddenText(page, label) {
  const text = await page.locator('body').innerText()
  const match = text.match(forbidden)
  if (match) throw new Error(`${label} exposed forbidden text: ${match[0]}`)
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch()

  const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const mobile = await mobileContext.newPage()
  mobile.setDefaultTimeout(10000)

  const mobileRoutes = [
    ['overview', '.trip-overview-shell'],
    ['today/2026-08-27', '.itinerary-workspace'],
    ['reservation', '.reservation-workspace'],
    ['food', '.food-workspace'],
    ['packing', '.packing-workspace'],
  ]
  for (const [route, selector] of mobileRoutes) {
    await openRoute(mobile, route, selector)
    await assertNoHorizontalOverflow(mobile, `390px ${route}`)
    await assertNoForbiddenText(mobile, route)
  }

  await openRoute(mobile, 'overview', '.trip-overview-shell')
  if ((await mobile.locator('.mobile-topbar-title').textContent())?.trim() !== '旅行總覽') throw new Error('mobile header should show only the current section')
  await mobile.locator('.menu-button').click()
  const drawerText = await mobile.locator('#mobile-navigation-drawer').innerText()
  if (/潮汐與動態|住宿安排與備註|預算與費用紀錄|資料來源|旅行資訊/.test(drawerText)) throw new Error('removed workflow still appears in navigation')
  await mobile.keyboard.press('Escape')

  for (const date of dates) {
    await openRoute(mobile, `today/${date}`, '.itinerary-workspace')
    if (await mobile.locator('.day-condition-grid > div').count() !== 6) throw new Error(`${date} does not show six practical condition cards`)
    if (await mobile.locator('.timeline-title-link').count() < 1) throw new Error(`${date} has no Google Maps title links`)
    if (await mobile.locator('.timeline-map-link, .map-icon-link').count()) throw new Error(`${date} still renders a large map icon button`)
    if (await mobile.locator('.day-alternative-group').count() !== 2) throw new Error(`${date} does not show rain and extra-time alternatives`)
    const hasTide = await mobile.locator('.day-tide-card').count() === 1
    if (hasTide !== (date === '2026-08-29' || date === '2026-08-30')) throw new Error(`${date} tide placement is incorrect`)
    await assertNoHorizontalOverflow(mobile, `390px today/${date}`)
    await assertNoForbiddenText(mobile, `today/${date}`)
  }

  await openRoute(mobile, 'today/2026-08-27', '.itinerary-workspace')
  const arrivalParking = mobile.locator('#item-day1-drive-garb-aeon .arrival-parking')
  await arrivalParking.waitFor()
  if (!(await arrivalParking.textContent())?.includes('商場停車場')) throw new Error('抵達前的交通卡缺少目的地停車資訊')
  if (await mobile.locator('#item-day1-night-shopping .arrival-parking').count()) throw new Error('停車資訊應放在抵達前的交通卡，不應在景點卡重複')

  await openRoute(mobile, 'today/2026-08-31', '.itinerary-workspace')
  const flightLink = mobile.locator('#item-day5-departure-flight .timeline-title-link')
  const flightHref = await flightLink.getAttribute('href')
  const flightQuery = flightHref ? new URL(flightHref).searchParams.get('query') : ''
  if (!flightQuery?.includes('神戸空港') || flightQuery.includes('桃園')) throw new Error(`Day 5 flight map target is wrong: ${flightQuery}`)

  await openRoute(mobile, 'packing', '.packing-workspace')
  if (await mobile.getByRole('checkbox').count()) throw new Error('packing page must not ask travelers to check tasks')
  if (await mobile.locator('textarea').count()) throw new Error('packing page must not ask travelers to enter notes')
  await mobile.getByText('暈船藥或暈車用品', { exact: true }).waitFor()

  await openRoute(mobile, 'reservation', '.reservation-workspace')
  if (await mobile.locator('.reservation-map-link, .map-icon-link, .reservation-card svg').count()) throw new Error('reservation page still renders map icon buttons')
  if (await mobile.locator('.reservation-card').count() !== 4) throw new Error('reservation count changed unexpectedly')

  await openRoute(mobile, 'food', '.food-workspace')
  await mobile.getByText('推薦餐點與飲品', { exact: true }).first().waitFor()
  await mobileContext.close()

  const desktopContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const desktop = await desktopContext.newPage()
  desktop.setDefaultTimeout(10000)
  for (const [route, selector] of mobileRoutes) {
    await openRoute(desktop, route, selector)
    await desktop.locator('.trip-sidebar').waitFor({ state: 'visible' })
    if ((await desktop.locator('.desktop-travelers').textContent())?.replace(/\s+/g, '') !== '旅客6大1小') throw new Error('desktop traveler summary is incorrect')
    await assertNoHorizontalOverflow(desktop, `1440px ${route}`)
    await assertNoForbiddenText(desktop, route)
  }
  await desktopContext.close()
} finally {
  await browser?.close()
  stop()
}
