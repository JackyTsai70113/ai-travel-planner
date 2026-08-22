import { ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { Bundle, toFriendlyStatus } from '../contracts/trip'
import { SectionDefinition } from '../app/route-registry'
import { DesktopSidebar } from './DesktopSidebar'
import { MobileHeader } from './MobileHeader'
import { MobileNavigation } from './MobileNavigation'

export type TripStatusType =
  | 'normal'
  | 'loading'
  | 'invalid'
  | 'critical'
  | 'offline-cache'
  | 'offline-no-cache'
  | 'newer-version'
  | 'route-not-found'

interface TripShellProps {
  bundle: Bundle | null
  shellStatus: TripStatusType
  tripVersion: string
  pageTitleId: string
  sections: SectionDefinition[]
  activeSection: string
  onNavigateSection: (nextSection: string) => void
  onRetry: () => void
  isDrawerOpen: boolean
  setDrawerOpen: (open: boolean) => void
  children: ReactNode
}

const statusText: Record<TripStatusType, string> = {
  normal: '狀態正常',
  loading: '資料載入中',
  invalid: '行程資料不可用',
  critical: '行程提醒：含關鍵警示',
  'offline-cache': '目前離線，使用快取資料',
  'offline-no-cache': '目前離線，無可用快取資料',
  'newer-version': '有可用新版，建議重整理',
  'route-not-found': '頁面不存在',
}

export default function TripShell({
  bundle,
  shellStatus,
  tripVersion,
  pageTitleId,
  sections,
  activeSection,
  onNavigateSection,
  onRetry,
  isDrawerOpen,
  setDrawerOpen,
  children,
}: TripShellProps) {
  const drawerRef = useRef<HTMLDivElement>(null)
  const [currentStatusText, setCurrentStatusText] = useState(statusText[shellStatus])

  useEffect(() => {
    setCurrentStatusText(statusText[shellStatus])
  }, [shellStatus])

  const title = bundle?.title ?? 'Golden Trip'
  const subtitle = bundle?.date_range
    ? `${bundle.date_range.start_date} ~ ${bundle.date_range.end_date}（${toFriendlyStatus(bundle.status)}）`
    : '行程資料載入中'

  useEffect(() => {
    if (isDrawerOpen) {
      const focusables = drawerRef.current?.querySelectorAll<HTMLElement>(
        'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      const first = focusables?.[0]
      const last = focusables?.[focusables.length - 1]
      first?.focus()

      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
          setDrawerOpen(false)
          return
        }

        if (event.key !== 'Tab' || !focusables || focusables.length === 0) return

        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first?.focus()
        }
      }

      window.addEventListener('keydown', onKeyDown)
      return () => window.removeEventListener('keydown', onKeyDown)
    }
  }, [isDrawerOpen, setDrawerOpen])

  const visibleState = useMemo(() => shellStatus !== 'normal', [shellStatus])
  const activeLabel = sections.find((section) => section.id === activeSection)?.label || '旅行總覽'
  const travelerText = bundle
    ? `${bundle.traveler_profile.adults} 大 ${bundle.traveler_profile.children_count} 小`
    : '旅客資料載入中'

  return (
    <div className={`app-shell ${visibleState ? 'with-alert' : ''}`}>
      <a className="skip-link" href="#trip-main">跳到主要內容</a>
      <MobileHeader
        title={title}
        subtitle={subtitle}
        onOpenMenu={() => setDrawerOpen(true)}
        statusText={currentStatusText}
        shellStatus={shellStatus}
      />

      <div className="app-frame">
        <DesktopSidebar
          sections={sections}
          activeSection={activeSection}
          onNavigate={onNavigateSection}
          title={title}
          subtitle={subtitle}
        />

        <main className="app-main" id="trip-main" aria-labelledby={pageTitleId}>
          <header className="desktop-topbar">
            <div><span className="desktop-topbar-section">{activeLabel}</span><span className="desktop-topbar-divider">/</span><span>{subtitle}</span></div>
            <div className="desktop-topbar-tools">
              <div className="desktop-quick-actions"><button type="button" onClick={() => onNavigateSection('today')}>今日行程</button><button type="button" onClick={() => onNavigateSection('map')}>導航</button></div>
              <span className="desktop-status"><i />{currentStatusText}</span><span className="desktop-travelers">{travelerText}</span>
            </div>
          </header>
          <header className="trip-main-header">
            <div className="main-title" id={pageTitleId}>
              {title}
            </div>
            <div className="shell-status-line">
              <span>{currentStatusText}</span>
              {shellStatus === 'newer-version' ? (
                <button type="button" onClick={onRetry}>
                  重新載入
                </button>
              ) : null}
            </div>
          </header>

          <section className="trip-content">
            <span className="trip-version">資料快照：{tripVersion || '--'}</span>
            {(shellStatus === 'invalid' || shellStatus === 'critical' || shellStatus === 'route-not-found') && (
              <p className="shell-message">
                {shellStatus === 'invalid'
                  ? '目前行程資料不可用，請稍後重試或回到其他 section。'
                  : shellStatus === 'critical'
                    ? '行程目前有關鍵提醒，建議先補齊行前缺漏後再啟程。'
                    : '此頁面不存在，將嘗試回到預設頁面。'}
              </p>
            )}

            {children}
          </section>
        </main>
      </div>

      <MobileNavigation sections={sections} activeSection={activeSection} onNavigate={onNavigateSection} />

      {isDrawerOpen ? (
        <div className="drawer-scrim" onClick={() => setDrawerOpen(false)} role="presentation">
          <aside className="mobile-drawer" role="dialog" aria-label="行程區段導覽" onClick={(event) => event.stopPropagation()} ref={drawerRef}>
            <div className="drawer-header">
              <h2>導航</h2>
              <button type="button" onClick={() => setDrawerOpen(false)} aria-label="關閉導覽">
                關閉
              </button>
            </div>
            <nav className="mobile-drawer-nav">
              {sections.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  className={`drawer-nav-item ${section.id === activeSection ? 'is-active' : ''}`}
                  onClick={() => {
                    onNavigateSection(section.id)
                    setDrawerOpen(false)
                  }}
                >
                  {section.label}
                </button>
              ))}
            </nav>
          </aside>
        </div>
      ) : null}
    </div>
  )
}
