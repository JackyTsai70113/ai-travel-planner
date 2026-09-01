const OBSOLETE_CACHE_PREFIX = 'awaji-2026-cache'

async function retireOfflineRuntime() {
  const cacheNames = await caches.keys()
  await Promise.all(cacheNames
    .filter((name) => name.startsWith(OBSOLETE_CACHE_PREFIX))
    .map((name) => caches.delete(name)))
  await self.registration.unregister()
  const clients = await self.clients.matchAll({ type: 'window' })
  await Promise.all(clients.map((client) => client.navigate(client.url)))
}

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting())
})

self.addEventListener('activate', (event) => {
  event.waitUntil(retireOfflineRuntime())
})
