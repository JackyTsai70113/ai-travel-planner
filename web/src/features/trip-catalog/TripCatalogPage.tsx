import { useMemo, useState } from 'react'
import type { TripCatalogEntry, TripRegistrySections } from '../../contracts/trip-registry'

type RouteSetter = (next: { route: 'home' | 'trip'; slug?: string }) => void

interface TripCatalogPageProps {
  catalog: TripCatalogEntry[]
  sections: TripRegistrySections
  setRoute: RouteSetter
  searchPlaceholder: string
}

interface FilterState {
  query: string
  year: string
  region: string
}

function filterItems(items: TripCatalogEntry[], filters: FilterState): TripCatalogEntry[] {
  const normalizedQuery = filters.query.trim().toLowerCase()
  return items.filter((entry) => {
    if (filters.region) {
      const inRegion = entry.destination_regions.some((region) => region.toLowerCase().includes(filters.region.toLowerCase()))
      if (!inRegion) return false
    }

    if (filters.year) {
      if (!entry.date_range.start_date.startsWith(filters.year) && !entry.date_range.end_date.startsWith(filters.year)) {
        return false
      }
    }

    if (!normalizedQuery) return true
    const haystack = [
      entry.title,
      entry.short_title,
      entry.destination_regions.join(' '),
      entry.tags.join(' '),
      entry.travelers_summary,
      entry.hero_summary,
      entry.theme_id,
    ].join(' ').toLowerCase()

    return haystack.includes(normalizedQuery)
  })
}

function statusText(status: string): string {
  if (status === 'published') return '已發布'
  if (status === 'preview') return '預覽'
  return '封存'
}

function readinessText(readiness: string): string {
  if (readiness === 'ready') return '可出發'
  if (readiness === 'incomplete') return '行前確認'
  return '阻斷'
}

function statusClass(status: string): string {
  if (status === 'published') return 'status-pill status-published'
  if (status === 'preview') return 'status-pill status-preview'
  return 'status-pill status-archived'
}

function readinessClass(readiness: string): string {
  if (readiness === 'ready') return 'status-pill status-ready'
  if (readiness === 'incomplete') return 'status-pill status-incomplete'
  return 'status-pill status-blocked'
}

function renderCard(item: TripCatalogEntry, setRoute: RouteSetter) {
  const fallbackMedia = item.cover_media.gradient || 'linear-gradient(130deg, #0f172a, #3a5a8f)'
  const hasImage = item.cover_media.kind === 'image' && item.cover_media.url
  const background = hasImage ? `linear-gradient(120deg, rgba(12,17,36,0.56), rgba(12,17,36,0.42)), url(${item.cover_media.url}) center/cover no-repeat` : fallbackMedia

  return (
    <article className="trip-card" key={item.slug}>
      <div className="trip-card-media" style={{ background }}>
        <span className={statusClass(item.status)}>{statusText(item.status)}</span>
        <span className={readinessClass(item.readiness)}>{readinessText(item.readiness)}</span>
      </div>
      <div className="trip-card-body">
        <p className="trip-card-eyebrow">{item.short_title}</p>
        <h3>{item.title}</h3>
        <p className="muted">{item.destination_regions.join(' / ')}</p>
        <p>{item.travelers_summary} • {item.duration_days} 天</p>
        <p className="muted">日期：{item.date_range.start_date} ~ {item.date_range.end_date}</p>
        <p>{item.hero_summary}</p>
        <div className="chips">
          {item.tags.map((tag) => (
            <span key={`${item.slug}-${tag}`} className="tag">
              {tag}
            </span>
          ))}
        </div>
        <p className="meta-note">關鍵提醒 {item.critical_alert_count} 則</p>
        <button type="button" onClick={() => setRoute({ route: 'trip', slug: item.slug })}>
          查看 trip
        </button>
      </div>
    </article>
  )
}

export default function TripCatalogPage({ catalog, sections, setRoute, searchPlaceholder }: TripCatalogPageProps) {
  const regions = useMemo(() => {
    return Array.from(new Set(catalog.flatMap((item) => item.destination_regions))).sort()
  }, [catalog])

  const years = useMemo(() => {
    const allYears = catalog.flatMap((item) => [
      item.date_range.start_date.slice(0, 4),
      item.date_range.end_date.slice(0, 4),
    ])
    return Array.from(new Set(allYears)).sort().reverse()
  }, [catalog])

  const [filters, setFilters] = useState<FilterState>({ query: '', year: '', region: '' })

  const filteredFeatured = filterItems(sections.featured, filters)
  const filteredUpcoming = filterItems(sections.upcoming, filters)
  const filteredPreview = filterItems(sections.preview, filters)
  const filteredArchived = filterItems(sections.archived, filters)
  const filteredAll = filterItems(catalog, filters)

  return (
    <div className="catalog-shell">
      <section className="search-shell card">
        <label htmlFor="trip-search">搜尋</label>
        <input
          id="trip-search"
          type="search"
          value={filters.query}
          placeholder={searchPlaceholder}
          onChange={(event) => setFilters((prev) => ({ ...prev, query: event.target.value }))}
        />
        <label htmlFor="trip-region">區域</label>
        <select
          id="trip-region"
          value={filters.region}
          onChange={(event) => setFilters((prev) => ({ ...prev, region: event.target.value }))}
        >
          <option value="">全部區域</option>
          {regions.map((region) => <option key={region} value={region}>{region}</option>)}
        </select>
        <label htmlFor="trip-year">年份</label>
        <select
          id="trip-year"
          value={filters.year}
          onChange={(event) => setFilters((prev) => ({ ...prev, year: event.target.value }))}
        >
          <option value="">全部年份</option>
          {years.map((year) => <option key={year} value={year}>{year}</option>)}
        </select>
      </section>

      {filteredAll.length === 0 ? <p className="muted">找不到符合條件的行程</p> : null}

      {filteredFeatured.length > 0 ? (
        <section className="catalog-section">
          <h2>精選 / 當前</h2>
          {filteredFeatured.map((item) => renderCard(item, setRoute))}
        </section>
      ) : null}
      {filteredUpcoming.length > 0 && (
        <section className="catalog-section">
          <h2>即將出發</h2>
          {filteredUpcoming.map((item) => renderCard(item, setRoute))}
        </section>
      )}
      {filteredPreview.length > 0 && (
        <section className="catalog-section">
          <h2>預覽 / 未完成</h2>
          {filteredPreview.map((item) => renderCard(item, setRoute))}
        </section>
      )}
      {filteredArchived.length > 0 && (
        <section className="catalog-section">
          <h2>封存 / 歷史</h2>
          {filteredArchived.map((item) => renderCard(item, setRoute))}
        </section>
      )}
      {filteredFeatured.length === 0 && filteredUpcoming.length === 0 && filteredPreview.length === 0 && filteredArchived.length === 0 && (
        <section className="catalog-section">
          <h2>全部行程</h2>
          {catalog.map((item) => renderCard(item, setRoute))}
        </section>
      )}
    </div>
  )
}
