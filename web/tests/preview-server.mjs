/* global process, fetch, setTimeout, URL */

import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const viteCli = fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url))

export function startPreviewServer({ args, baseUrl, attempts = 40 }) {
  const server = spawn(process.execPath, [viteCli, 'preview', ...args, '--strictPort'], { stdio: ['ignore', 'pipe', 'pipe'] })
  server.unref()

  let serverFailure = null
  let serverReady = false
  let stopping = false
  let serverOutput = ''

  const observeOutput = (chunk, target) => {
    target.write(chunk)
    serverOutput = `${serverOutput}${chunk.toString()}`.slice(-4_000)
    if (serverOutput.includes('Local') && serverOutput.includes('127.0.0.1')) serverReady = true
  }

  server.stdout.on('data', (chunk) => observeOutput(chunk, process.stdout))
  server.stderr.on('data', (chunk) => observeOutput(chunk, process.stderr))
  server.once('error', (error) => { serverFailure = error })
  server.once('exit', (code, signal) => {
    if (!stopping) {
      serverFailure = new Error(`預覽伺服器在驗證前結束：code=${code}, signal=${signal}`)
    }
  })

  const stop = () => {
    stopping = true
    if (server.exitCode === null && server.signalCode === null) server.kill('SIGTERM')
  }
  process.on('exit', stop)

  const waitForServer = async () => {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (serverFailure) throw serverFailure
      if (serverReady) {
        try {
          if ((await fetch(baseUrl)).ok) return
        } catch {
          if (serverFailure) throw serverFailure
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    if (serverFailure) throw serverFailure
    throw new Error('本次預覽伺服器未在時限內啟動')
  }

  return { stop, waitForServer }
}
