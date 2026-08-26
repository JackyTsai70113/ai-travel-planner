/* global document */

import { chromium } from 'playwright'
import { copyFileSync, cpSync, mkdirSync, readdirSync } from 'node:fs'
import { startPreviewServer } from './preview-server.mjs'

copyFileSync(new URL('../public/trips/awaji-2026/public-bundle.json', import.meta.url), new URL('../dist/public-bundle.json', import.meta.url))
mkdirSync(new URL('../dist/trips/awaji-2026/', import.meta.url), { recursive: true })
copyFileSync(new URL('../public/trips/awaji-2026/public-bundle.json', import.meta.url), new URL('../dist/trips/awaji-2026/public-bundle.json', import.meta.url))
for (const item of readdirSync(new URL('../dist/', import.meta.url))) {
  if (item === 'trips') continue
  cpSync(new URL(`../dist/${item}`, import.meta.url), new URL(`../dist/trips/awaji-2026/${item}`, import.meta.url), { recursive: true })
}

const deploymentPath = '/ai-travel-planner/'
const baseUrl = `http://127.0.0.1:4181${deploymentPath}trips/awaji-2026/`
const routes = [
  'overview',
  ...['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31'].map((date) => `today/${date}`),
  'reservation',
  'food',
  'packing',
  'japanese',
]
const { stop, waitForServer } = startPreviewServer({
  args: ['--base', deploymentPath, '--host', '127.0.0.1', '--port', '4181'],
  baseUrl,
})

function assertMapsShape(rawUrl) {
  const url = new URL(rawUrl)
  if (!/(^|\.)google\.com$/.test(url.hostname) || !url.pathname.startsWith('/maps/')) return
  const decodedUrl = decodeURIComponent(url.toString())
  if (/undefined|null|兵庫県淡路市志筑字黒田/i.test(decodedUrl)) throw new Error(`Google Maps 查詢含無效值：${decodedUrl}`)
  if (url.pathname.startsWith('/maps/search') && !url.searchParams.get('query')) throw new Error(`Google Maps 搜尋缺少 query：${url}`)
  if (url.pathname.startsWith('/maps/dir') && (!url.searchParams.get('origin') || !url.searchParams.get('destination'))) throw new Error(`Google Maps 路線缺少起訖點：${url}`)
}

async function verifyGoogleMapsTargets(browser, urls) {
  const mapsUrls = urls.filter((rawUrl) => {
    const url = new URL(rawUrl)
    return /(^|\.)google\.com$/.test(url.hostname) && url.pathname.startsWith('/maps/')
  })
  let cursor = 0
  const failures = []
  const workers = Array.from({ length: 3 }, async () => {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })
    while (cursor < mapsUrls.length) {
      const url = mapsUrls[cursor]
      cursor += 1
      try {
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 })
        await page.waitForFunction(() => {
          const main = document.querySelector('[role="main"]')
          return document.title.length > 0 && (main?.textContent?.trim().length || 0) > 20
        }, { timeout: 10_000 })
        const title = await page.title()
        const text = await page.locator('body').innerText()
        const mainText = await page.locator('[role="main"]').first().innerText()
        const blocked = /Before you continue to Google|在繼續前往 Google 之前|unusual traffic|異常流量|not a robot|CAPTCHA/i.test(`${title}\n${text}`)
        const missing = /Google (?:地圖|Maps)(?:目前)?找不到|找不到路線|No results found|could(?: not|n't) find/i.test(text)
        const isRoute = new URL(url).pathname.startsWith('/maps/dir')
        const routeResolved = isRoute && /(?:\d+\s*(?:分|分鐘|小時|min|hr)|\d+(?:[.,]\d+)?\s*(?:公里|km))/i.test(mainText)
        const placeResolved = !isRoute && /結果|營業|評論|地址|路線|Results|Open|Closed|reviews|Directions/i.test(mainText)
        const resolved = / - Google (?:地圖|Maps)$/i.test(title) || routeResolved || placeResolved
        if (blocked || missing || !resolved) failures.push(`${url}（標題：${title || '空白'}）`)
      } catch (error) {
        failures.push(`${url} (${String(error)})`)
      }
    }
    await page.close()
  })
  await Promise.all(workers)
  if (failures.length) throw new Error(`Google Maps 找不到下列目標：\n${failures.join('\n')}`)
}

async function requestWithRetry(url) {
  let lastError
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch(url, {
        redirect: 'follow',
        signal: AbortSignal.timeout(20_000),
        headers: { 'user-agent': 'Mozilla/5.0 (compatible; ai-travel-planner-link-check/1.0)' },
      })
      await response.body?.cancel()
      if (response.status < 400) return { url, status: response.status, finalUrl: response.url }
      lastError = new Error(`HTTP ${response.status}`)
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 250 * attempt))
  }
  throw new Error(`${url}：${String(lastError)}`)
}

let browser
try {
  await waitForServer()
  browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const externalUrls = new Set()
  for (const route of routes) {
    await page.goto(`${baseUrl}#/${route}`, { waitUntil: 'domcontentloaded' })
    await page.locator('.trip-content').waitFor({ state: 'visible' })
    const links = await page.locator('a[target="_blank"]').evaluateAll((anchors) => anchors.map((anchor) => anchor.href))
    links.filter((href) => href.startsWith('https://')).forEach((href) => externalUrls.add(href))
  }

  const urls = [...externalUrls]
  urls.forEach(assertMapsShape)
  let cursor = 0
  const results = []
  const workers = Array.from({ length: 4 }, async () => {
    while (cursor < urls.length) {
      const url = urls[cursor]
      cursor += 1
      results.push(await requestWithRetry(url))
    }
  })
  await Promise.all(workers)
  await verifyGoogleMapsTargets(browser, urls)
  console.log(JSON.stringify({ checked: results.length, status: 'PASS' }))
} finally {
  await browser?.close()
  stop()
}
