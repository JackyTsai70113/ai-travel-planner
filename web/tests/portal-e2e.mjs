import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { copyFileSync, cpSync, mkdirSync, readdirSync } from 'node:fs'

for (const slug of ['awaji-2026', 'kansai-preview-2025']) {
  mkdirSync(`dist/trips/${slug}`, { recursive: true })
  copyFileSync('dist/index.html', `dist/trips/${slug}/index.html`)
  for (const item of readdirSync('dist')) {
    if (item === 'index.html' || item === 'trips') continue
    cpSync(`dist/${item}`, `dist/trips/${slug}/${item}`, { recursive: true })
  }
}

const baseUrl = 'http://127.0.0.1:4174/'
const server = spawn('npm', ['run', 'preview', '--', '--host', '127.0.0.1', '--port', '4174'], { stdio: 'inherit' })
const stop = () => server.kill('SIGTERM')
process.on('exit', stop)

async function waitForServer() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      if ((await fetch(baseUrl)).ok) return
    } catch {
      // Preview server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  throw new Error('portal preview server did not start')
}

const browser = await chromium.launch()
try {
  await waitForServer()
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await page.goto(baseUrl, { waitUntil: 'networkidle' })
  await page.locator('.trip-card').nth(1).waitFor({ state: 'visible' })
  if (await page.locator('.trip-card').count() !== 2) throw new Error('root catalog did not render both recorded trips')
  if (await page.locator('h1').filter({ hasText: 'AI Travel Planner' }).count() !== 1) throw new Error('root product identity missing')
  await page.locator('.trip-card').filter({ hasText: 'Awaji 2026' }).getByRole('button', { name: '查看 trip' }).click()
  await page.locator('.trip-overview-shell').waitFor({ state: 'visible' })
  if (!page.url().includes('/trips/awaji-2026/')) throw new Error(`Awaji URL was not canonical: ${page.url()}`)
  if ((await page.title()).includes('Trip Planner')) throw new Error('trip metadata was not updated')
  await page.goto(`${baseUrl}trips/kansai-preview-2025/`, { waitUntil: 'networkidle' })
  await page.locator('.trip-overview-shell').waitFor({ state: 'visible' })
  if ((await page.locator('.status-preview').count()) < 1) throw new Error('preview status was not rendered')
} finally {
  await browser.close()
}
