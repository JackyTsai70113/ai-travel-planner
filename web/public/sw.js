const CACHE_PREFIX = 'awaji-2026-cache'
const DEFAULT_CACHE_NAME = `${CACHE_PREFIX}-bootstrap`
const APP_MANIFEST = 'manifest.webmanifest'
const APP_BUNDLE = 'public-bundle.json'
const APP_REGISTRY = 'trip-registry.json'
const OFFLINE_PAGE = 'offline.html'
const SW_MESSAGE_UPDATE = 'awaji-cache-update'
const SW_MESSAGE_SYNC = 'awaji-sync'

let activeCacheName = DEFAULT_CACHE_NAME
const APP_SHELL_FILES = [
  './',
  './index.html',
  './manifest.webmanifest',
  `./${APP_MANIFEST}`,
  `./${APP_BUNDLE}`,
  `./${APP_REGISTRY}`,
  `./${OFFLINE_PAGE}`,
]

function isJsonResponse(response) {
  const contentType = response.headers.get('content-type') || ''
  return contentType.includes('application/json')
}

async function readBundleVersion(response) {
  if (!response || !isJsonResponse(response)) return null
  try {
    const payload = await response.clone().json()
    if (!isValidPublicBundle(payload)) return null
    return (
      payload.meta?.bundle_sha256 ||
      payload.meta?.source_sha256 ||
      payload.meta?.generated_at ||
      payload.trip_id ||
      'no-version'
    )
  } catch {
    return null
  }
}

function isValidPublicBundle(payload) {
  if (!payload || typeof payload !== 'object') return false
  if (typeof payload.trip_id !== 'string') return false
  if (!payload.meta || typeof payload.meta !== 'object') return false
  if (!payload.days || !Array.isArray(payload.days)) return false
  return true
}

function hashToCacheName(base) {
  const safeBase = (base || 'fallback').trim()
  return `${CACHE_PREFIX}-${safeBase}`.slice(0, 110)
}

async function ensureActiveCacheName() {
  if (activeCacheName !== DEFAULT_CACHE_NAME) return activeCacheName
  try {
    const response = await fetch(APP_BUNDLE, { cache: 'no-store' })
    if (!response.ok) return activeCacheName
    const payload = await response.clone().json()
    if (!isValidPublicBundle(payload)) return activeCacheName
    const version = payload.meta?.bundle_sha256 || payload.meta?.source_sha256 || payload.meta?.generated_at
    if (!version) return activeCacheName
    activeCacheName = hashToCacheName(version)
    return activeCacheName
  } catch {
    return activeCacheName
  }
}

function normalizeManifestPath(value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  if (trimmed === '.') return './'
  if (trimmed === '/') return './'
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return trimmed
  }
  if (trimmed.startsWith('/')) {
    return `.${trimmed}`
  }
  return `./${trimmed.replace(/^\.\/+/, '')}`
}

async function notifyClients(type, detail = {}) {
  const clients = await self.clients.matchAll()
  for (const client of clients) {
    client.postMessage({ type, ...detail })
  }
}

async function ensurePreCache() {
  const cacheName = await ensureActiveCacheName()
  const cache = await caches.open(cacheName)
  try {
    await cache.addAll(APP_SHELL_FILES)
  } catch {
    // no-op: allow install even if one shell asset temporarily missing
  }

  const manifestFiles = await collectManifestAssets()
  for (const entry of manifestFiles) {
    try {
      await cache.add(entry)
    } catch {
      // no-op
    }
  }

  try {
    const bundleResponse = await fetch(APP_BUNDLE, { cache: 'no-store' })
    if (!bundleResponse.ok) {
      await notifyClients(SW_MESSAGE_SYNC, { state: 'bundle_fetch_failed', cacheReady: true })
      return
    }
    const bundleVersion = await readBundleVersion(bundleResponse.clone())
    const bundleJsonResponse = bundleResponse.clone()
    if (bundleVersion) {
      await cache.put(`./${APP_BUNDLE}`, bundleJsonResponse)
      await notifyClients(SW_MESSAGE_SYNC, { state: 'bundle_updated', version: bundleVersion, cacheReady: true })
    }
  } catch {
    await notifyClients(SW_MESSAGE_SYNC, { state: 'bundle_fetch_failed', cacheReady: true })
  }
}

async function cleanupOldCaches(currentName) {
  const keys = await caches.keys()
  await Promise.all(
    keys.map((key) => {
      if (key.startsWith(CACHE_PREFIX) && key !== currentName) {
        return caches.delete(key)
      }
      return Promise.resolve()
    }),
  )
}

async function collectManifestAssets() {
  const assets = new Set([
    './',
    './index.html',
    `./${APP_BUNDLE}`,
    `./${OFFLINE_PAGE}`,
    `./${APP_MANIFEST}`,
  ])
  try {
    const manifestResponse = await fetch(`./${APP_MANIFEST}`, { cache: 'no-store' })
    if (!manifestResponse.ok) return [...assets]
    const manifest = await manifestResponse.json()
    if (!manifest || typeof manifest !== 'object') return [...assets]

    const addAsset = (value) => {
      const normalized = normalizeManifestPath(value)
      if (normalized) {
        assets.add(normalized)
      }
    }

    addAsset(manifest.start_url)
    addAsset(manifest.scope)
    if (manifest.icons && Array.isArray(manifest.icons)) {
      for (const icon of manifest.icons) {
        if (!icon || typeof icon !== 'object') continue
        addAsset(icon.src)
      }
    }

    if (Array.isArray(manifest.shortcuts)) {
      for (const shortcut of manifest.shortcuts) {
        if (!shortcut || typeof shortcut !== 'object') continue
        addAsset(shortcut.url)
        if (Array.isArray(shortcut.icons)) {
          for (const icon of shortcut.icons) {
            if (!icon || typeof icon !== 'object') continue
            addAsset(icon.src)
          }
        }
      }
    }
  } catch {
    // no-op: keep app shell fallback
  }
  return [...assets]
}

async function cacheFirst(request) {
  const cacheName = await ensureActiveCacheName()
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request)
  if (cached) return cached

  try {
    const response = await fetch(request)
    if (response.ok) {
      const copy = response.clone()
      cache.put(request, copy)
    }
    return response
  } catch {
    return null
  }
}

async function networkFirstBundle(request, requestUrl) {
  const cacheName = await ensureActiveCacheName()
  const cache = await caches.open(cacheName)
  const cacheHit = await cache.match(request)
  let previousVersion = null
  if (cacheHit) {
    previousVersion = await readBundleVersion(cacheHit.clone())
  }

  try {
    const response = await fetch(request, { cache: 'no-store' })
    if (!response.ok) throw new Error(`bundle-http-${response.status}`)
    const bundleJson = await response.clone().json()
    if (!isValidPublicBundle(bundleJson)) {
      throw new Error('bundle-invalid')
    }
    const version = await readBundleVersion(response.clone())
    if (version) {
      const nextCacheName = hashToCacheName(version)
      if (nextCacheName !== activeCacheName) {
        const nextCache = await caches.open(nextCacheName)
        await nextCache.put(request, response.clone())
        const previousCacheName = activeCacheName
        activeCacheName = nextCacheName
        await cleanupOldCaches(activeCacheName)
        if (previousCacheName !== activeCacheName) {
          await caches.delete(previousCacheName)
        }
      } else {
        await cache.put(request, response.clone())
      }
      if (previousVersion && previousVersion !== version) {
        await notifyClients(SW_MESSAGE_UPDATE, {
          state: 'bundle_updated',
          version,
          previousVersion,
          url: requestUrl.href,
        })
      } else {
        await notifyClients(SW_MESSAGE_SYNC, {
          state: 'bundle_synced',
          version,
          url: requestUrl.href,
        })
      }
    }
    return response
  } catch (error) {
    if (cacheHit) {
      await notifyClients(SW_MESSAGE_SYNC, {
        state: 'bundle_offline',
        url: requestUrl.href,
        message: String(error instanceof Error ? error.message : error),
      })
      return cacheHit
    }
    throw error
  }
}

async function navigateRequest(request) {
  const cacheName = await ensureActiveCacheName()
  const cache = await caches.open(cacheName)
  try {
    const response = await fetch(request)
    if (response.ok) {
      cache.put(request, response.clone())
    }
    return response
  } catch {
    const cachedShell = await cache.match('./')
    const cachedOffline = await cache.match(`./${OFFLINE_PAGE}`)
    return cachedShell || cachedOffline || new Response('offline', { status: 503, statusText: 'offline' })
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      await ensurePreCache()
      await cleanupOldCaches(activeCacheName)
      self.skipWaiting()
    })(),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      await cleanupOldCaches(activeCacheName)
      await self.clients.claim()
    })(),
  )
})

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return
  const requestUrl = new URL(event.request.url)
  if (requestUrl.origin !== self.location.origin) return
  if (requestUrl.pathname.includes('/sw.js')) return

  if (requestUrl.pathname.endsWith(`/${APP_BUNDLE}`)) {
    event.respondWith(networkFirstBundle(event.request, requestUrl))
    return
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(navigateRequest(event.request))
    return
  }

  if (
    event.request.destination === 'style' ||
    event.request.destination === 'script' ||
    event.request.destination === 'font' ||
    event.request.destination === 'image' ||
    event.request.destination === 'manifest' ||
    event.request.destination === 'document' ||
    event.request.destination === 'worker'
  ) {
    event.respondWith(
      cacheFirst(event.request).then((response) => response || fetch(event.request)),
    )
    return
  }

  event.respondWith(
    fetch(event.request).catch(async () => {
      const cacheName = await ensureActiveCacheName()
      const cache = await caches.open(cacheName)
      const cached = await cache.match(event.request)
      return cached || cache.match(`./${OFFLINE_PAGE}`)
    }),
  )
})
