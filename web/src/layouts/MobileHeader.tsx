import type { RefObject } from 'react'
import { TripStatusType } from './TripShell'

interface MobileHeaderProps {
  title: string
  subtitle: string
  onOpenMenu: () => void
  isMenuOpen: boolean
  menuButtonRef: RefObject<HTMLButtonElement>
  statusText: string
  shellStatus: TripStatusType
}

const LABEL_BY_STATUS: Record<TripStatusType, string> = {
  loading: '資料載入中',
  invalid: '資料異常',
  critical: '異常提示',
  'offline-cache': '離線快取可用',
  'offline-no-cache': '離線無快取',
  'newer-version': '有新版可用',
  'route-not-found': '頁面不存在',
  normal: '正常',
}

export function MobileHeader({ title, subtitle, onOpenMenu, isMenuOpen, menuButtonRef, statusText, shellStatus }: MobileHeaderProps) {
  return (
    <header className="mobile-topbar">
      <button
        className="menu-button"
        type="button"
        onClick={onOpenMenu}
        aria-label="展開導覽選單"
        aria-expanded={isMenuOpen}
        aria-controls="mobile-navigation-drawer"
        ref={menuButtonRef}
      >
        <span className="menu-icon" aria-hidden="true"><span /><span /><span /></span>
      </button>
      <div className="mobile-topbar-title">
        <p>{title}</p>
        <small>{subtitle}</small>
      </div>
      <span className={`mobile-status ${shellStatus}`}>{statusText || LABEL_BY_STATUS[shellStatus]}</span>
    </header>
  )
}
