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
const baseUrl = `http://127.0.0.1:4181${deploymentPath}trips/awaji-2026/`
const routes = [
  'overview',
  ...['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31'].map((date) => `today/${date}`),
  'reservation',
  'food',
  'packing',
  'japanese',
]
const server = spawn('npm', ['run', 'preview', '--', '--base', deploymentPath, '--host', '127.0.0.1', '--port', '4181'], { stdio: 'inherit' })
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

function assertMapsShape(rawUrl) {
  const url = new URL(rawUrl)
  if (!/(^|\.)google\.com$/.test(url.hostname) || !url.pathname.startsWith('/maps/')) return
  if (/undefined|null|兵庫県淡路市志筑字黒田/i.test(url.toString())) throw new Error(`Google Maps 查詢含無效值：${url}`)
  if (url.pathname.startsWith('/maps/search') && !url.searchParams.get('query')) throw new Error(`Google Maps 搜尋缺少 query：${url}`)
  if (url.pathname.startsWith('/maps/dir') && (!url.searchParams.get('origin') || !url.searchParams.get('destination'))) throw new Error(`Google Maps 路線缺少起訖點：${url}`)
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
  console.log(JSON.stringify({ checked: results.length, status: 'PASS' }))
} finally {
  await browser?.close()
  stop()
}
