import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

type SwStatusPayload = {
  status: 'unknown' | 'registering' | 'ready' | 'failed' | 'unsupported'
  message?: string
}

function publishServiceWorkerStatus(status: SwStatusPayload['status'], message = ''): void {
  const detail: SwStatusPayload = { status, message }
  const typedWindow = window as Window & { __awaji_sw_status__?: SwStatusPayload }
  typedWindow.__awaji_sw_status__ = detail
  window.dispatchEvent(new CustomEvent('awaji-sw-status', { detail }))
}

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

if ('serviceWorker' in navigator) {
  publishServiceWorkerStatus('registering', '準備註冊 Service Worker')
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(`${import.meta.env.BASE_URL}sw.js`)
      .then(() => {
        publishServiceWorkerStatus('ready', 'Service Worker 已啟用，可離線讀取核心內容')
      })
      .catch((error) => {
        publishServiceWorkerStatus('failed', String(error instanceof Error ? error.message : 'Service Worker 註冊失敗'))
      })
  })
} else {
  publishServiceWorkerStatus('unsupported', '此環境不支援 Service Worker')
}
