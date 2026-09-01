import { chromium } from 'playwright'
import { copyFileSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { startPreviewServer } from './preview-server.mjs'

copyFileSync(new URL('../public/trips/awaji-2026/public-bundle.json', import.meta.url), new URL('../dist/public-bundle.json', import.meta.url))
mkdirSync(new URL('../dist/trips/awaji-2026/', import.meta.url), { recursive: true })
copyFileSync(new URL('../public/trips/awaji-2026/public-bundle.json', import.meta.url), new URL('../dist/trips/awaji-2026/public-bundle.json', import.meta.url))
for (const item of readdirSync(new URL('../dist/', import.meta.url))) {
  if (item === 'trips') continue
  cpSync(new URL(`../dist/${item}`, import.meta.url), new URL(`../dist/trips/awaji-2026/${item}`, import.meta.url), { recursive: true })
}
const staleWorkerSource = "self.addEventListener('install', (event) => event.waitUntil(self.skipWaiting()))"
writeFileSync(new URL('../dist/trips/awaji-2026/stale-worker.js', import.meta.url), staleWorkerSource)
writeFileSync(new URL('../dist/unrelated-worker.js', import.meta.url), staleWorkerSource)

const deploymentPath = '/ai-travel-planner/'
const baseUrl = `http://127.0.0.1:4173${deploymentPath}trips/awaji-2026/`
const dates = ['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31']
const forbidden = /待補|未提供|未知|官方未公布|狀態正常|規劃估計|硬截止|硬離場|Sheet 指定|家庭／無障礙|聯絡[／/]參考|Canonical Trip|Golden Trip|\bloading\b|資料快照|熱中症|UTC|資料來源|旅行資訊|只提供出發前閱讀|不要求旅途中/i
const serviceWorkerSource = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')
if (!serviceWorkerSource.includes('registration.unregister()') || serviceWorkerSource.includes("addEventListener('fetch'")) throw new Error('舊版離線快取仍會攔截網頁請求')
if (existsSync(new URL('../public/offline.html', import.meta.url))) throw new Error('舊版離線頁仍存在')
const staticDescriptionMarker = '__TRIP_HERO_SUMMARY__'
const builtIndexSource = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
const markerCount = builtIndexSource.split(staticDescriptionMarker).length - 1
if (markerCount !== 2) throw new Error(`靜態旅程描述標記應出現兩次，實際為 ${markerCount}`)
const registry = JSON.parse(readFileSync(new URL('../public/trip-registry.json', import.meta.url), 'utf8'))
const awajiSummary = registry.find((trip) => trip.slug === 'awaji-2026')?.hero_summary
const deployedAwajiIndex = builtIndexSource.replaceAll(staticDescriptionMarker, awajiSummary)
if (!awajiSummary || (deployedAwajiIndex.match(new RegExp(`content="${awajiSummary}"`, 'g')) || []).length !== 2) {
  throw new Error('部署後的靜態 description 與 og:description 未換成淡路島旅程摘要')
}
const { stop, waitForServer } = startPreviewServer({
  args: ['--base', deploymentPath, '--host', '127.0.0.1', '--port', '4173'],
  baseUrl,
})

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

async function assertNoOverlap(page, leftSelector, rightSelector, label) {
  const [left, right] = await Promise.all([page.locator(leftSelector).boundingBox(), page.locator(rightSelector).boundingBox()])
  if (!left || !right) throw new Error(`${label} missing overlap target`)
  const overlapWidth = Math.max(0, Math.min(left.x + left.width, right.x + right.width) - Math.max(left.x, right.x))
  const overlapHeight = Math.max(0, Math.min(left.y + left.height, right.y + right.height) - Math.max(left.y, right.y))
  if (overlapWidth > 0 && overlapHeight > 0) throw new Error(`${label} overlaps by ${overlapWidth}x${overlapHeight}`)
}

async function assertNoElementCollisions(page, selector, label) {
  const rectangles = await page.locator(selector).evaluateAll((elements) => elements
    .filter((element) => {
      const style = getComputedStyle(element)
      return style.display !== 'none' && style.visibility !== 'hidden'
    })
    .map((element) => {
      const bounds = element.getBoundingClientRect()
      return { left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom }
    }))
  for (let leftIndex = 0; leftIndex < rectangles.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < rectangles.length; rightIndex += 1) {
      const left = rectangles[leftIndex]
      const right = rectangles[rightIndex]
      const overlapWidth = Math.max(0, Math.min(left.right, right.right) - Math.max(left.left, right.left))
      const overlapHeight = Math.max(0, Math.min(left.bottom, right.bottom) - Math.max(left.top, right.top))
      if (overlapWidth > 0 && overlapHeight > 0) throw new Error(`${label} elements ${leftIndex + 1} and ${rightIndex + 1} overlap by ${overlapWidth}x${overlapHeight}`)
    }
  }
}

async function assertVerticalFlow(page, selectors, label) {
  const sections = []
  for (const selector of selectors) {
    const element = page.locator(selector).first()
    if (await element.count() && await element.isVisible()) {
      const bounds = await element.boundingBox()
      if (bounds) sections.push({ selector, top: bounds.y, bottom: bounds.y + bounds.height })
    }
  }
  for (let index = 1; index < sections.length; index += 1) {
    if (sections[index].top < sections[index - 1].bottom) {
      throw new Error(`${label} ${sections[index].selector} overlaps ${sections[index - 1].selector}`)
    }
  }
}

async function assertViewportGutter(page, selector, label, minimum = 15) {
  const result = await page.locator(selector).first().evaluate((element) => {
    const bounds = element.getBoundingClientRect()
    return { left: bounds.left, right: window.innerWidth - bounds.right }
  })
  if (result.left < minimum || result.right < minimum) {
    throw new Error(`${label} viewport gutter is ${result.left}px / ${result.right}px`)
  }
}

async function assertCardPadding(page, selector, label, minimum = 16) {
  const violations = await page.locator(selector).evaluateAll((elements, minimumPadding) => elements.map((element) => {
    const style = getComputedStyle(element)
    return {
      left: Number.parseFloat(style.paddingLeft),
      right: Number.parseFloat(style.paddingRight),
    }
  }).filter((padding) => padding.left < minimumPadding || padding.right < minimumPadding), minimum)
  if (violations.length) throw new Error(`${label} card padding is too small: ${JSON.stringify(violations)}`)
}

async function assertVerticalCardGap(page, selector, label, minimum = 14) {
  const gaps = await page.locator(selector).evaluateAll((elements) => {
    const rectangles = elements.map((element) => element.getBoundingClientRect()).sort((a, b) => a.top - b.top)
    return rectangles.slice(1).map((current, index) => current.top - rectangles[index].bottom)
  })
  const violation = gaps.find((gap) => gap < minimum)
  if (violation !== undefined) throw new Error(`${label} vertical card gap is ${violation}px`)
}

async function assertCompactConditionSummary(page, label) {
  const conditionLayout = await page.locator('.day-condition-grid').evaluate((grid) => {
    const bounds = grid.getBoundingClientRect()
    const cards = [...grid.children].map((card) => {
      const cardBounds = card.getBoundingClientRect()
      const style = getComputedStyle(card)
      return {
        top: Math.round(cardBounds.top),
        width: cardBounds.width,
        paddingLeft: Number.parseFloat(style.paddingLeft),
        paddingRight: Number.parseFloat(style.paddingRight),
      }
    })
    return { height: bounds.height, width: bounds.width, cards }
  })
  const [weather, rain, heat, activity, driving, fixed] = conditionLayout.cards
  if (
    weather.top !== rain.top ||
    heat.width < conditionLayout.width * 0.9 ||
    activity.width < conditionLayout.width * 0.9 ||
    driving.top !== fixed.top ||
    conditionLayout.height > 760 ||
    conditionLayout.cards.some((card) => card.paddingLeft > 14 || card.paddingRight > 14)
  ) throw new Error(`${label} mobile condition summary is still oversized: ${JSON.stringify(conditionLayout)}`)
}

async function assertExternalLinksOpen(page, selector, label) {
  const links = page.locator(selector)
  const count = await links.count()
  await page.context().route('https://**/*', (route) => route.fulfill({ status: 200, contentType: 'text/html', body: '<title>external target</title>' }))
  try {
    for (let index = 0; index < count; index += 1) {
      const link = links.nth(index)
      const href = await link.getAttribute('href')
      if (!href) throw new Error(`${label} link ${index + 1} has no href`)
      await link.scrollIntoViewIfNeeded()
      const popupPromise = page.waitForEvent('popup')
      await link.click()
      const popup = await popupPromise
      await popup.waitForLoadState('domcontentloaded')
      if (new URL(popup.url()).toString() !== new URL(href).toString()) throw new Error(`${label} link ${index + 1} opened ${popup.url()} instead of ${href}`)
      await popup.close()
    }
  } finally {
    await page.context().unroute('https://**/*')
  }
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch()

  const loadingContext = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const loadingPage = await loadingContext.newPage()
  await loadingPage.route('**/public-bundle.json', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_000))
    await route.continue()
  })
  await loadingPage.goto(baseUrl, { waitUntil: 'domcontentloaded' })
  await loadingPage.locator('.desktop-topbar').waitFor({ state: 'visible' })
  await assertNoForbiddenText(loadingPage, '行程載入畫面')
  await loadingContext.close()

  // 從入口頁與行程頁模擬過期 Worker，確認只清除目前行程，不影響同網域其他網站。
  const staleCacheCleanupContext = await browser.newContext()
  const staleCacheCleanupPage = await staleCacheCleanupContext.newPage()
  await staleCacheCleanupPage.goto(`http://127.0.0.1:4173${deploymentPath}`, { waitUntil: 'domcontentloaded' })
  await staleCacheCleanupPage.evaluate(async () => {
    await navigator.serviceWorker.register('trips/awaji-2026/stale-worker.js', { scope: 'trips/awaji-2026/' })
    await navigator.serviceWorker.register('unrelated-worker.js', { scope: 'unrelated/' })
  })
  await staleCacheCleanupPage.waitForFunction(async () => (await navigator.serviceWorker.getRegistrations()).length === 2)
  await staleCacheCleanupPage.reload({ waitUntil: 'domcontentloaded' })
  await staleCacheCleanupPage.waitForFunction(async () => (await navigator.serviceWorker.getRegistrations()).length === 2)
  await assertNoForbiddenText(staleCacheCleanupPage, '入口網站')
  await staleCacheCleanupPage.goto(baseUrl, { waitUntil: 'domcontentloaded' })
  await staleCacheCleanupPage.waitForFunction(async () => {
    const registrations = await navigator.serviceWorker.getRegistrations()
    return registrations.length === 1 && new URL(registrations[0].scope).pathname.endsWith('/ai-travel-planner/unrelated/')
  })
  await staleCacheCleanupPage.evaluate(async () => {
    await Promise.all((await navigator.serviceWorker.getRegistrations()).map((registration) => registration.unregister()))
  })
  await staleCacheCleanupContext.close()

  const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const mobile = await mobileContext.newPage()
  mobile.setDefaultTimeout(10000)

  const mobileRoutes = [
    ['overview', '.trip-overview-shell'],
    ...dates.map((date) => [`today/${date}`, '.itinerary-workspace']),
    ['reservation', '.reservation-workspace'],
    ['food', '.food-workspace'],
    ['packing', '.packing-workspace'],
    ['japanese', 'section.card[aria-label="實用日文"]'],
  ]
  const mobileCardSelectors = {
    overview: '.trip-overview-hero, .overview-section, .overview-day-card',
    today: '.day-hero, .timeline-card, .day-alternative-group',
    reservation: '.reservation-card',
    food: '.food-card',
    packing: '.packing-guide-card > header, .packing-guide-card ul',
    japanese: 'section.card[aria-label="實用日文"], .phrase-list .subcard',
  }
  const mobileGapSelectors = {
    overview: '.overview-day-card',
    reservation: '.reservation-card',
    food: '.food-card',
    packing: '.packing-guide-card',
    japanese: '.phrase-list .subcard',
  }
  const mobileCollisionSelectors = {
    overview: '.overview-day-card',
    today: '.day-tab, .day-condition-grid > div, .day-media figure, .timeline-card, .day-alternative-group article',
    reservation: '.reservation-card',
    food: '.food-card',
    packing: '.packing-guide-card',
    japanese: '.phrase-list .subcard',
  }
  for (const width of [375, 390, 430]) {
    await mobile.setViewportSize({ width, height: 844 })
    for (const [route, selector] of mobileRoutes) {
      await openRoute(mobile, route, selector)
      const routeKind = route.startsWith('today/') ? 'today' : route
      if (await mobile.locator('.trip-sidebar').isVisible()) throw new Error(`${width}px ${route} still shows the desktop sidebar`)
      await assertNoHorizontalOverflow(mobile, `${width}px ${route}`)
      await assertViewportGutter(mobile, selector, `${width}px ${route}`)
      await assertCardPadding(mobile, mobileCardSelectors[routeKind], `${width}px ${route}`)
      if (mobileGapSelectors[routeKind]) await assertVerticalCardGap(mobile, mobileGapSelectors[routeKind], `${width}px ${route}`)
      await assertNoElementCollisions(mobile, mobileCollisionSelectors[routeKind], `${width}px ${route}`)
      if (routeKind === 'today') await assertCompactConditionSummary(mobile, `${width}px ${route}`)
      if (routeKind === 'today') await assertVerticalFlow(mobile, ['.itinerary-day-nav', '.day-hero', '.day-media', '.daily-route-map', '.itinerary-utility', '.timeline', '.day-alternatives'], `${width}px ${route}`)
      await assertNoForbiddenText(mobile, route)
    }
  }

  await mobile.setViewportSize({ width: 390, height: 844 })

  await openRoute(mobile, 'overview', '.trip-overview-shell')
  const overviewDayLayout = await mobile.locator('.overview-day-card').first().evaluate((card) => {
    const number = card.querySelector('.overview-day-number')?.getBoundingClientRect()
    const copy = card.querySelector('.overview-day-copy')?.getBoundingClientRect()
    return number && copy ? { numberBottom: number.bottom, copyTop: copy.top } : null
  })
  if (!overviewDayLayout || overviewDayLayout.copyTop - overviewDayLayout.numberBottom < 13) throw new Error('mobile overview day card is still cramped')
  if (await mobile.locator('.overview-day-foot').count()) throw new Error('overview day card repeats lodging information')
  const firstDayCard = mobile.locator('.overview-day-card').first()
  const firstDayLodgingCount = ((await firstDayCard.innerText()).match(/Awaji Riverside Terrace in Shizuki 780/g) || []).length
  if (firstDayLodgingCount !== 1) throw new Error(`overview first day repeats lodging ${firstDayLodgingCount} times`)
  if ((await mobile.locator('.mobile-topbar-title').textContent())?.trim() !== '旅行總覽') throw new Error('mobile header should show only the current section')
  await mobile.locator('.menu-button').click()
  const drawerText = await mobile.locator('#mobile-navigation-drawer').innerText()
  if (/潮汐與動態|住宿安排與備註|預算與費用紀錄|資料來源|旅行資訊/.test(drawerText)) throw new Error('removed workflow still appears in navigation')
  await mobile.keyboard.press('Escape')

  for (const date of dates) {
    await openRoute(mobile, `today/${date}`, '.itinerary-workspace')
    if (await mobile.locator('.day-condition-grid > div').count() !== 6) throw new Error(`${date} does not show six practical condition cards`)
    if (await mobile.locator('.map-pin-link').count() < 1) throw new Error(`${date} has no map pin links`)
    if (await mobile.locator('.timeline-map-link, .map-icon-link, .parking-map-link, .official-info-link').count()) throw new Error(`${date} still renders duplicate map or official text buttons`)
    const repeatedParkingFacts = await mobile.locator('.timeline-entry.transport-leg').evaluateAll((cards) => cards.flatMap((card) => {
      const destinationCard = card.nextElementSibling
      const parkingText = destinationCard?.querySelector('.parking-fact-link')?.textContent?.trim() || ''
      return parkingText && card.textContent?.includes(parkingText) ? [parkingText] : []
    }))
    if (repeatedParkingFacts.length) throw new Error(`${date} 交通卡重複目的地停車資訊：${repeatedParkingFacts.join('、')}`)
    const parkingPairs = await mobile.locator('.timeline-entry:not(.transport-leg):has(.parking-fact-link)').evaluateAll((cards) => cards.map((card) => {
      const placeHref = card.querySelector('.map-pin-link')?.getAttribute('href') || ''
      const parkingHref = card.querySelector('.parking-fact-link')?.getAttribute('href') || ''
      const placeQuery = placeHref ? new URL(placeHref).searchParams.get('query') || '' : ''
      const parkingQuery = parkingHref ? new URL(parkingHref).searchParams.get('query') || '' : ''
      return { placeHref, parkingHref, placeQuery, parkingQuery }
    }))
    if (parkingPairs.some(({ placeHref, parkingHref, placeQuery, parkingQuery }) => !placeHref || !parkingHref || placeHref === parkingHref || /駐車場|parking/i.test(placeQuery) || !/駐車場|parking/i.test(parkingQuery))) throw new Error(`${date} 景點與停車場連結混用：${JSON.stringify(parkingPairs)}`)
    const dayTabs = await mobile.locator('.day-tab').evaluateAll((tabs) => tabs.map((tab) => {
      const day = tab.querySelector('strong')?.getBoundingClientRect()
      const date = tab.querySelector('span')?.getBoundingClientRect()
      return { text: tab.textContent || '', verticalDifference: day && date ? Math.abs(day.top - date.top) : 999 }
    }))
    if (dayTabs.some(({ text, verticalDifference }) => /0\d-\d{2}/.test(text) || verticalDifference > 3)) throw new Error(`${date} day tabs wrap or use an unclear date format: ${JSON.stringify(dayTabs)}`)
    if (await mobile.locator('.day-alternative-group').count() !== 2) throw new Error(`${date} does not show rain and extra-time alternatives`)
    const hasTide = await mobile.locator('.day-tide-card').count() === 1
    if (hasTide !== (date === '2026-08-29' || date === '2026-08-30')) throw new Error(`${date} tide placement is incorrect`)
    await assertNoHorizontalOverflow(mobile, `390px today/${date}`)
    await assertNoForbiddenText(mobile, `today/${date}`)
  }

  await openRoute(mobile, 'today/2026-08-27', '.itinerary-workspace')
  const shoppingCard = mobile.locator('#item-day1-night-shopping')
  if (!(await shoppingCard.textContent())?.includes('473 台免費平面停車場')) throw new Error('目的地卡缺少具名停車資訊')
  const shoppingPlaceHref = await shoppingCard.locator('.map-pin-link').getAttribute('href')
  const shoppingParkingHref = await shoppingCard.locator('.parking-fact-link').getAttribute('href')
  if (!shoppingPlaceHref?.includes('maps/search') || !shoppingParkingHref?.includes('maps/search')) throw new Error('目的地或停車場 Google Maps 連結缺漏')
  if (shoppingPlaceHref === shoppingParkingHref || !/AEON Awaji|イオン淡路店/i.test(new URL(shoppingPlaceHref).searchParams.get('query') || '') || !new URL(shoppingParkingHref).searchParams.get('query')?.includes('駐車場')) throw new Error(`景點與停車場連結混用：${shoppingPlaceHref} / ${shoppingParkingHref}`)
  if (await mobile.locator('.day-lodging-card').count()) throw new Error('住宿摘要與照片卡仍然重複')
  if (await mobile.locator('.day-media').getByText('Awaji Riverside Terrace in Shizuki 780', { exact: true }).count() !== 1) throw new Error('住宿照片卡應只顯示一次住宿名稱')
  if (await mobile.locator('.day-media .media-title-link[href*="booking.com"]').count()) throw new Error('住宿名稱不應連到第三方訂房平台')
  const mediaGaps = await mobile.locator('.day-media figure').evaluateAll((figures) => figures.map((figure) => {
    const caption = figure.querySelector('figcaption')?.getBoundingClientRect()
    const bounds = figure.getBoundingClientRect()
    return caption ? bounds.bottom - caption.bottom : 999
  }))
  if (mediaGaps.some((gap) => gap > 2)) throw new Error(`照片卡仍有拉伸空白：${mediaGaps.join(', ')}`)
  const routeBHref = await mobile.getByRole('link', { name: '開啟路線B' }).getAttribute('href')
  const routeBDestination = routeBHref ? new URL(routeBHref).searchParams.get('destination') : ''
  if (!routeBDestination?.includes('Awaji Riverside Terrace Shizuki 780-12') || routeBDestination.includes('兵庫県淡路市志筑字黒田')) throw new Error(`路線 B 仍使用無法解析的飯店地址：${routeBDestination}`)

  await openRoute(mobile, 'today/2026-08-31', '.itinerary-workspace')
  const flightLink = mobile.locator('#item-day5-departure-flight .map-pin-link')
  const flightHref = await flightLink.getAttribute('href')
  const flightQuery = flightHref ? new URL(flightHref).searchParams.get('query') : ''
  if (!/神戸空港|Kobe Airport/i.test(flightQuery || '') || flightQuery?.includes('桃園')) throw new Error(`Day 5 flight map target is wrong: ${flightQuery}`)

  await openRoute(mobile, 'packing', '.packing-workspace')
  if (await mobile.getByRole('checkbox').count()) throw new Error('packing page must not ask travelers to check tasks')
  if (await mobile.locator('textarea').count()) throw new Error('packing page must not ask travelers to enter notes')
  await mobile.getByText('暈船藥或暈車用品', { exact: true }).waitFor()

  await openRoute(mobile, 'reservation', '.reservation-workspace')
  if (await mobile.locator('.reservation-map-link, .map-icon-link').count()) throw new Error('預約頁仍顯示舊版地圖按鈕')
  if (await mobile.locator('.reservation-card .map-pin-link').count() !== 4) throw new Error('reservation page should render one map pin for each reservation')
  if (await mobile.locator('.reservation-card').count() !== 4) throw new Error('reservation count changed unexpectedly')

  await openRoute(mobile, 'food', '.food-workspace')
  await mobile.getByText('推薦餐點與飲品', { exact: true }).first().waitFor()
  const foodParkingPairs = await mobile.locator('.food-card:has(.parking-fact-link)').evaluateAll((cards) => cards.map((card) => {
    const placeHref = card.querySelector('.map-pin-link')?.getAttribute('href') || ''
    const parkingHref = card.querySelector('.parking-fact-link')?.getAttribute('href') || ''
    const placeQuery = placeHref ? new URL(placeHref).searchParams.get('query') || '' : ''
    const parkingQuery = parkingHref ? new URL(parkingHref).searchParams.get('query') || '' : ''
    return { placeHref, parkingHref, placeQuery, parkingQuery }
  }))
  if (foodParkingPairs.some(({ placeHref, parkingHref, placeQuery, parkingQuery }) => !placeHref || !parkingHref || placeHref === parkingHref || /駐車場|parking/i.test(placeQuery) || !/駐車場|parking/i.test(parkingQuery))) throw new Error(`餐飲頁景點與停車場連結混用：${JSON.stringify(foodParkingPairs)}`)
  await mobileContext.close()

  const desktopContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const desktop = await desktopContext.newPage()
  desktop.setDefaultTimeout(10000)
  let sidebarCollapsed = false
  for (const [route, selector] of mobileRoutes) {
    await openRoute(desktop, route, selector)
    await desktop.locator('.trip-sidebar').waitFor({ state: 'visible' })
    if (await desktop.locator('.desktop-travelers').count()) throw new Error('desktop should not repeat traveler count')
    if (!sidebarCollapsed) {
      const collapseButton = desktop.getByRole('button', { name: '收合側欄' })
      const before = await collapseButton.boundingBox()
      await collapseButton.click()
      if (!(await desktop.locator('.trip-sidebar').evaluate((element) => element.classList.contains('is-collapsed')))) throw new Error('desktop sidebar did not collapse')
      const expandButton = desktop.getByRole('button', { name: '展開側欄' })
      const after = await expandButton.boundingBox()
      if (!before || !after || Math.abs(before.y - after.y) > 1) throw new Error(`sidebar control moved vertically: ${before?.y} -> ${after?.y}`)
      await expandButton.click()
      sidebarCollapsed = true
    }
    await assertNoHorizontalOverflow(desktop, `1440px ${route}`)
    await assertNoForbiddenText(desktop, route)
  }

  for (const width of [1200, 1366, 1440, 1920]) {
    await desktop.setViewportSize({ width, height: 1000 })
    await openRoute(desktop, 'overview', '.trip-overview-shell')
    await assertNoOverlap(desktop, '.trip-hero-content', '.hero-route-map', `${width}px overview hero`)
    const heroOverflow = await desktop.locator('.trip-hero-content').evaluate((element) => element.scrollWidth > element.clientWidth + 1)
    if (heroOverflow) throw new Error(`${width}px overview content overflows its grid column`)
    await openRoute(desktop, 'today/2026-08-27', '.itinerary-workspace')
    const photoHeights = await desktop.locator('.day-media figure').evaluateAll((figures) => figures.map((figure) => figure.getBoundingClientRect().height))
    if (Math.max(...photoHeights) - Math.min(...photoHeights) > 1) throw new Error(`${width}px 同列照片卡高度不一致：${photoHeights.join(', ')}`)
    const shinobiTitleLayout = await desktop.locator('.day-media strong[title*="Nijigen no Mori"]').evaluate((element) => {
      const textNode = element.firstChild?.nodeType === Node.TEXT_NODE ? element.firstChild : element.querySelector('a')?.firstChild
      const text = textNode?.textContent || ''
      const firstIndex = text.indexOf('忍')
      const secondIndex = text.indexOf('里')
      if (!textNode || firstIndex < 0 || secondIndex < 0) return { text, sameLine: false }
      const first = document.createRange()
      first.setStart(textNode, firstIndex)
      first.setEnd(textNode, firstIndex + 1)
      const second = document.createRange()
      second.setStart(textNode, secondIndex)
      second.setEnd(textNode, secondIndex + 1)
      return { text, sameLine: Math.abs(first.getBoundingClientRect().top - second.getBoundingClientRect().top) <= 1 }
    })
    if (shinobiTitleLayout.text !== 'NARUTO & BORUTO 忍里' || !shinobiTitleLayout.sameLine) throw new Error(`${width}px 忍里標題斷行不正確：${JSON.stringify(shinobiTitleLayout)}`)
  }

  await desktop.setViewportSize({ width: 1440, height: 1000 })
  for (const date of dates) {
    await openRoute(desktop, `today/${date}`, '.itinerary-workspace')
    await desktop.locator('.day-media').scrollIntoViewIfNeeded()
    await desktop.waitForFunction(() => [...document.querySelectorAll('.day-media img')].every((image) => image.complete && image.naturalWidth > 0))
    await assertExternalLinksOpen(desktop, '.daily-route-links a, .timeline-place-heading > h3 a, .timeline-place-heading > .map-pin-link, .parking-fact-link', `${date} primary external`)
  }
  await openRoute(desktop, 'today/2026-08-27', '.itinerary-workspace')
  await desktop.locator('.day-media').scrollIntoViewIfNeeded()
  await desktop.waitForFunction(() => [...document.querySelectorAll('.day-media img')].every((image) => image.complete && image.naturalWidth > 0))
  const mediaCards = await desktop.locator('.day-media figure').evaluateAll((figures) => figures.map((figure) => ({
    height: figure.getBoundingClientRect().height,
    titleHeight: figure.querySelector('figcaption strong')?.getBoundingClientRect().height || 0,
    lineHeight: Number.parseFloat(getComputedStyle(figure.querySelector('figcaption strong')).lineHeight),
  })))
  const mediaHeights = mediaCards.map(({ height }) => height)
  if (Math.max(...mediaHeights) - Math.min(...mediaHeights) > 1) throw new Error(`同列照片卡高度不一致：${mediaHeights.join(', ')}`)
  if (mediaCards.some(({ titleHeight, lineHeight }) => titleHeight > lineHeight * 2 + 1)) throw new Error(`照片卡標題超過兩行：${JSON.stringify(mediaCards)}`)
  const shinobiPhoto = desktop.locator('.day-media img[alt*="忍里"]')
  if (!(await shinobiPhoto.getAttribute('src'))?.includes('aba1dd9afd994bc383f5259806be7bb4')) throw new Error('忍里仍使用裝飾性佔位圖片')
  await openRoute(desktop, 'food', '.food-workspace')
  await assertExternalLinksOpen(desktop, '.food-place-heading > h3 a, .food-place-heading > .map-pin-link, .food-card .parking-fact-link', 'food primary external')
  await openRoute(desktop, 'reservation', '.reservation-workspace')
  await assertExternalLinksOpen(desktop, '.reservation-title-row > h2 a, .reservation-title-row > .map-pin-link', 'reservation primary external')
  await desktopContext.close()
} finally {
  await browser?.close()
  stop()
}
