import { sitePageUrl } from '../app/site-links'

export function LegalLinks({ className = '' }: { className?: string }) {
  return <nav className={`legal-links ${className}`.trim()} aria-label="法律資訊">
    <a href={sitePageUrl('terms')}>使用條款</a>
    <a href={sitePageUrl('privacy')}>隱私權政策</a>
  </nav>
}
