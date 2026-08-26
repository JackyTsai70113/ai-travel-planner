import type { RefObject } from 'react'
import { TripStatusType } from './TripShell'

interface MobileHeaderProps {
  sectionLabel: string
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
  'route-not-found': '頁面不存在',
  normal: '',
}

export function MobileHeader({ sectionLabel, onOpenMenu, isMenuOpen, menuButtonRef, statusText, shellStatus }: MobileHeaderProps) {
  return (
    <header className="mobile-topbar">
      <button
        className="menu-button"
        type="button"
        onClick={onOpenMenu}
        aria-label={isMenuOpen ? '導覽選單已展開' : '展開導覽選單'}
        aria-expanded={isMenuOpen}
        aria-controls="mobile-navigation-drawer"
        ref={menuButtonRef}
      >
        <span className="menu-icon" aria-hidden="true"><span /><span /><span /></span>
      </button>
      <div className="mobile-topbar-title">
        <p>{sectionLabel}</p>
      </div>
      {shellStatus !== 'normal' ? <span className={`mobile-status ${shellStatus}`}>{statusText || LABEL_BY_STATUS[shellStatus]}</span> : null}
    </header>
  )
}
