import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import SiteRouter from './app/site-router'
import './styles.css'
import './responsive.css'

async function removeStaleOfflineCache() {
  if ('serviceWorker' in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations()
    const appPath = new URL(import.meta.env.BASE_URL, window.location.href).pathname
    await Promise.all(registrations
      .filter((registration) => new URL(registration.scope).pathname.startsWith(appPath))
      .map((registration) => registration.unregister()))
  }

  if ('caches' in window) {
    const cacheNames = await window.caches.keys()
    await Promise.all(cacheNames
      .filter((name) => name.startsWith('awaji-2026-cache'))
      .map((name) => window.caches.delete(name)))
  }
}

void removeStaleOfflineCache()

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <SiteRouter />
  </StrictMode>,
)
