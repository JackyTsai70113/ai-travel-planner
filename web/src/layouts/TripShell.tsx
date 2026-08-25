import { ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { Bundle } from '../contracts/trip'
import { SectionDefinition } from '../app/route-registry'
import { DesktopSidebar } from './DesktopSidebar'
import { MobileHeader } from './MobileHeader'

export type TripStatusType =
  | 'normal'
  | 'loading'
  | 'invalid'
  | 'critical'
  | 'offline-cache'
  | 'offline-no-cache'
  | 'route-not-found'

interface TripShellProps {
  bundle: Bundle | null
  shellStatus: TripStatusType
  pageTitleId: string
  sections: SectionDefinition[]
  activeSection: string
  onNavigateSection: (nextSection: string) => void
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
  'route-not-found': '頁面不存在',
}

export default function TripShell({
  bundle,
  shellStatus,
  pageTitleId,
  sections,
  activeSection,
  onNavigateSection,
  isDrawerOpen,
  setDrawerOpen,
  children,
}: TripShellProps) {
  const drawerRef = useRef<HTMLDivElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const wasDrawerOpen = useRef(isDrawerOpen)
  const [currentStatusText, setCurrentStatusText] = useState(statusText[shellStatus])

  useEffect(() => {
    setCurrentStatusText(statusText[shellStatus])
  }, [shellStatus])

  const title = bundle?.title ?? 'Golden Trip'
  const subtitle = bundle?.date_range
    ? `${bundle.date_range.start_date} ~ ${bundle.date_range.end_date}`
    : '行程資料載入中'

  useEffect(() => {
    if (!isDrawerOpen && wasDrawerOpen.current && window.matchMedia('(max-width: 960px)').matches) {
      menuButtonRef.current?.focus()
    }
    wasDrawerOpen.current = isDrawerOpen
  }, [isDrawerOpen])

  useEffect(() => {
    const desktopViewport = window.matchMedia('(min-width: 961px)')
    const closeDrawerOnDesktop = (matches: boolean) => {
      if (matches) setDrawerOpen(false)
    }
    const onViewportChange = (event: MediaQueryListEvent) => closeDrawerOnDesktop(event.matches)

    closeDrawerOnDesktop(desktopViewport.matches)
    desktopViewport.addEventListener('change', onViewportChange)
    return () => desktopViewport.removeEventListener('change', onViewportChange)
  }, [setDrawerOpen])

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
        isMenuOpen={isDrawerOpen}
        menuButtonRef={menuButtonRef}
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
            <div className="desktop-topbar-tools"><span className="desktop-status"><i />{currentStatusText}</span><span className="desktop-travelers"><small>旅客</small>{travelerText}</span></div>
          </header>
          <header className="trip-main-header">
            <div className="main-title" id={pageTitleId}>
              {title}
            </div>
            <div className="shell-status-line">
              <span>{currentStatusText}</span>
            </div>
          </header>

          <section className="trip-content">
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

      {isDrawerOpen ? (
        <div className="drawer-scrim" onClick={() => setDrawerOpen(false)} role="presentation">
          <aside
            className="mobile-drawer"
            id="mobile-navigation-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mobile-navigation-title"
            onClick={(event) => event.stopPropagation()}
            ref={drawerRef}
          >
            <div className="drawer-header">
              <h2 id="mobile-navigation-title">導航</h2>
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
                  aria-current={section.id === activeSection ? 'page' : undefined}
                  onClick={() => {
                    onNavigateSection(section.id)
                    setDrawerOpen(false)
                  }}
                >
                  <span>{section.label}</span>
                  {section.id === activeSection ? <small>目前</small> : null}
                </button>
              ))}
            </nav>
          </aside>
        </div>
      ) : null}
    </div>
  )
}
