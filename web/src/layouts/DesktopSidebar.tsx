import { SectionDefinition } from '../app/route-registry'

interface DesktopSidebarProps {
  sections: SectionDefinition[]
  activeSection: string
  onNavigate: (next: string) => void
  title: string
}

const sectionIcons: Record<string, string> = {
  overview: '⌂',
  today: '◷',
  map: '⌖',
  reservation: '◇',
  food: '♨',
  packing: '✓',
  japanese: 'あ',
}

export function DesktopSidebar({ sections, activeSection, onNavigate, title }: DesktopSidebarProps) {
  return (
    <aside className="trip-sidebar" aria-label="主要導覽">
      <div className="trip-brand">
        <h1 className="trip-brand-title"><span aria-hidden="true">🌊</span>{title}</h1>
      </div>
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
            <span className="trip-nav-copy"><strong>{section.label}</strong></span>
          </button>
        ))}
      </nav>
    </aside>
  )
}
