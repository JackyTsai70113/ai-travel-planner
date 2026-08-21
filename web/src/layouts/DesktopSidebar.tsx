import { SectionDefinition } from '../app/route-registry'

interface DesktopSidebarProps {
  sections: SectionDefinition[]
  activeSection: string
  onNavigate: (next: string) => void
  title: string
  subtitle: string
}

export function DesktopSidebar({ sections, activeSection, onNavigate, title, subtitle }: DesktopSidebarProps) {
  return (
    <aside className="trip-sidebar" aria-label="主要導覽">
      <div className="trip-brand">
        <p className="trip-brand-kicker"><span>✦</span> Trip Planner · 2026</p>
        <h1 className="trip-brand-title">{title}</h1>
        <p className="trip-brand-subtitle">{subtitle}</p>
      </div>
      <div className="trip-sidebar-status"><span>●</span><div><strong>旅途中可用行程</strong><small>公開資料與待補狀態會明確標示</small></div></div>
      <p className="trip-nav-label">主控選單</p>
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
            <span>{section.label}</span>
            <small>{section.description}</small>
          </button>
        ))}
      </nav>
    </aside>
  )
}
