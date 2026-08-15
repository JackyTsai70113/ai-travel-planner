const CACHE_NAME = 'awaji-2026-cache-v1'

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return
  const url = new URL(event.request.url)
  if (url.origin !== self.location.origin) return
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
      const copy = response.clone()
      if (response.status === 200) {
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy))
      }
      return response
    }).catch(() => cached))
  )
})
