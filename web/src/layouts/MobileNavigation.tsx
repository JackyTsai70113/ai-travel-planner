import { SectionDefinition } from '../app/route-registry'

interface MobileNavigationProps {
  sections: SectionDefinition[]
  activeSection: string
  onNavigate: (next: string) => void
}

export function MobileNavigation({ sections, activeSection, onNavigate }: MobileNavigationProps) {
  return (
    <nav className="mobile-bottom-nav" aria-label="底部導覽">
      <div className="mobile-bottom-track">
        {sections.map((section) => (
          <button
            key={section.id}
            type="button"
            className={`bottom-nav-item ${section.id === activeSection ? 'is-active' : ''}`}
            aria-current={section.id === activeSection ? 'page' : undefined}
            onClick={() => onNavigate(section.id)}
          >
            {section.label}
          </button>
        ))}
      </div>
    </nav>
  )
}
