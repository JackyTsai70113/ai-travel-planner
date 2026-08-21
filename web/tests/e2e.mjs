import { chromium } from 'playwright'
import { spawn } from 'node:child_process'

const server = spawn('npm', ['run', 'preview', '--', '--host', '127.0.0.1', '--port', '4173'], { stdio: 'inherit' })
const stop = () => server.kill('SIGTERM')
process.on('exit', stop)
try {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const response = await fetch('http://127.0.0.1:4173/')
      if (response.ok) break
    } catch {
      // preview server is still starting
    }
    await new Promise((resolve) => setTimeout(resolve, 100))
    if (attempt === 29) throw new Error('preview server did not start')
  }
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  page.setDefaultTimeout(10000)
  await page.goto('http://127.0.0.1:4173/#/overview', { waitUntil: 'domcontentloaded' })
  await page.locator('.app-shell').waitFor()
  await page.locator('#trip-main').waitFor({ state: 'attached' })
  await page.goto('http://127.0.0.1:4173/#/sources', { waitUntil: 'domcontentloaded' })
  await page.locator('h1, h2').filter({ hasText: '資料來源' }).waitFor({ state: 'attached' })
  await page.goto('http://127.0.0.1:4173/#/today', { waitUntil: 'domcontentloaded' })
  await page.locator('.app-shell').waitFor({ state: 'attached' })
  if (!page.url().includes('#/today')) throw new Error(`today route was not preserved: ${page.url()}`)
  await browser.close()
} finally {
  stop()
}
