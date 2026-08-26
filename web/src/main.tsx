import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import SiteRouter from './app/site-router'
import './styles.css'

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <SiteRouter />
  </StrictMode>,
)
