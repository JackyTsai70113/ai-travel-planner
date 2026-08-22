import { SectionDefinition } from '../app/route-registry'

interface DesktopSidebarProps {
  sections: SectionDefinition[]
  activeSection: string
  onNavigate: (next: string) => void
  title: string
  subtitle: string
}

const sectionIcons: Record<string, string> = {
  overview: '⌂',
  today: '◷',
  map: '⌖',
  reservation: '◇',
  tides: '≈',
  food: '♨',
  lodging: '▣',
  handbook: '＋',
  packing: '✓',
  budget: '¥',
  japanese: 'あ',
  sources: '↗',
}

export function DesktopSidebar({ sections, activeSection, onNavigate, title, subtitle }: DesktopSidebarProps) {
  return (
    <aside className="trip-sidebar" aria-label="主要導覽">
      <div className="trip-brand">
        <p className="trip-brand-kicker"><span>✦</span> SETOUCHI · 2026</p>
        <h1 className="trip-brand-title">{title}</h1>
        <p className="trip-brand-subtitle">{subtitle}</p>
      </div>
      <div className="trip-sidebar-status"><span>●</span><div><strong>五日旅行手冊</strong><small>行程、住宿、導航與行前清單集中管理</small></div></div>
      <p className="trip-nav-label">TRIP MENU</p>
      <nav className="trip-nav" aria-label="行程區段">
        {sections.map((section) => (
          <button
            key={section.id}
            type="button"
            className={`trip-nav-item ${section.id === activeSection ? 'is-active' : ''}`}
            aria-current={section.id === activeSection ? 'page' : undefined}
            onClick={() => onNavigate(section.id)}
            data-depth={section.dayScoped ? 0 : 1}
          >
            <span className="trip-nav-icon" aria-hidden="true">{sectionIcons[section.id] || '·'}</span>
            <span className="trip-nav-copy"><strong>{section.label}</strong><small>{section.description}</small></span>
          </button>
        ))}
      </nav>
      <footer className="trip-sidebar-footer"><span>●</span><p>已快取內容可離線閱讀<br /><small>導航需連線開啟 Google Maps</small></p></footer>
    </aside>
  )
}
