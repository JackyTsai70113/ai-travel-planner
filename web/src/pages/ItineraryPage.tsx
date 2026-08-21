import { useMemo, useState } from 'react'
import { Bundle, BundleDayItem, buildMapsLink, findPlaceAddress, findPlaceLabel } from '../contracts/trip'
import { buildRoutePath, TripRoute } from '../app/route-registry'

interface ItineraryPageProps { bundle: Bundle; route: TripRoute; onNavigate: (next: Partial<TripRoute>) => void }

function parseMinutes(value: string | null): number | null {
  if (!value) return null
  const match = value.match(/(\d{1,2}):(\d{2})/)
  return match ? Number(match[1]) * 60 + Number(match[2]) : null
}

function itemState(item: BundleDayItem): string[] {
  const states: string[] = []
  if (item.fixed || item.kind === 'reservation' || item.kind === 'flight') states.push('固定')
  if (item.optional || item.kind === 'optional' || item.notes?.toLowerCase().includes('optional')) states.push('可選')
  if (item.cancelable || item.notes?.includes('可取消')) states.push('可取消')
  if (item.unresolved || !item.start_at || !item.end_at) states.push('待補')
  return states.length ? states : ['已確認']
}

function highlight(value: string, query: string): JSX.Element {
  if (!query) return <>{value}</>
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return <>{value.split(new RegExp(`(${escaped})`, 'ig')).map((part, index) => part.toLowerCase() === query.toLowerCase() ? <mark key={index}>{part}</mark> : part)}</>
}

export function ItineraryPage({ bundle, route, onNavigate }: ItineraryPageProps) {
  const [copiedId, setCopiedId] = useState('')
  const [query, setQuery] = useState('')
  const [plan, setPlan] = useState<'A' | 'B' | 'C'>('A')
  const [quickMode, setQuickMode] = useState<'all' | 'now' | 'next'>('all')
  const [showPrintView, setShowPrintView] = useState(false)
  const selectedDay = bundle.days.find((day) => day.date === route.day) ?? (route.day && Number(route.day) > 0 ? bundle.days[Number(route.day) - 1] : undefined) ?? bundle.days[0]
  const currentMinutes = useMemo(() => {
    if (!selectedDay || selectedDay.date !== new Date().toISOString().slice(0, 10)) return null
    const now = new Date(); return now.getHours() * 60 + now.getMinutes()
  }, [selectedDay])
  const nowIndex = selectedDay?.items.findIndex((item) => { const start = parseMinutes(item.start_at); const end = parseMinutes(item.end_at); return currentMinutes != null && start != null && end != null && currentMinutes >= start && currentMinutes <= end }) ?? -1
  const nextIndex = selectedDay?.items.findIndex((item) => { const start = parseMinutes(item.start_at); return currentMinutes != null && start != null && start >= currentMinutes }) ?? -1
  const visibleItems = selectedDay?.items.filter((_, index) => quickMode === 'now' ? index === nowIndex : quickMode === 'next' ? index === nextIndex : true) ?? []
  const normalizedQuery = query.trim().toLowerCase()
  const searchResults = useMemo(() => !normalizedQuery ? [] : bundle.days.flatMap((day, dayIndex) => day.items.flatMap((item) => {
    const place = bundle.places?.find((candidate) => candidate.id === item.place_id)
    const text = [day.date, day.summary, item.id, item.kind, item.notes, place?.name, place?.name_ja, place?.address].filter(Boolean).join(' ').toLowerCase()
    return text.includes(normalizedQuery) ? [{ day, dayIndex, item, label: place?.name || item.place_id }] : []
  })), [bundle.days, bundle.places, normalizedQuery])
  const metrics = useMemo(() => ({
    attractions: selectedDay?.items.filter((item) => ['attraction', 'sightseeing', 'poi'].includes(item.kind)).length ?? 0,
    optional: selectedDay?.items.filter((item) => item.optional || item.kind === 'optional').length ?? 0,
    unresolved: selectedDay?.items.filter((item) => item.unresolved || !item.start_at || !item.end_at).length ?? 0,
  }), [selectedDay])
  const alternatives = (bundle.alternatives || []).filter((alternative) => (alternative.plan || 'A') === plan)
  if (!selectedDay) return <section className="card">沒有可顯示的行程日。</section>
  const copyText = async (label: string, text: string) => { try { await navigator.clipboard.writeText(text); setCopiedId(label); setTimeout(() => setCopiedId(''), 1200) } catch { setCopiedId('error') } }
  const navigateTo = (day: string, item?: string) => onNavigate({ section: 'today', day, item })
  return <section className={`card itinerary-workspace ${showPrintView ? 'print-itinerary' : ''}`} aria-label="每日行程工作區">
    <div className="itinerary-toolbar"><div><h2>互動行程工作區</h2><p className="muted">{bundle.date_range.start_date} ~ {bundle.date_range.end_date} · 時區 {bundle.local_timezone || 'unknown'}</p></div><button type="button" onClick={() => setShowPrintView((value) => !value)}>{showPrintView ? '返回操作模式' : '列印完整行程'}</button></div>
    <div className="day-tabs" role="tablist" aria-label="行程日程頁籤">{bundle.days.map((day, index) => <button key={day.date} className={`day-tab ${day.date === selectedDay.date ? 'active' : ''}`} role="tab" aria-selected={day.date === selectedDay.date} onClick={() => navigateTo(day.date)} type="button">Day {index + 1}<span>{day.date}</span></button>)}</div>
    {!showPrintView && <div className="itinerary-search"><label htmlFor="itinerary-search">搜尋全行程</label><input id="itinerary-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="中文／日文／地址／備註／category" />{searchResults.length > 0 && <ul className="search-results">{searchResults.map(({ day, dayIndex, item, label }) => <li key={`${day.date}-${item.id}`}><button type="button" onClick={() => navigateTo(day.date, item.id)}>{highlight(`${day.date} · ${label} · ${item.kind}`, query)}</button><span>{dayIndex + 1} 日</span></li>)}</ul>}{normalizedQuery && !searchResults.length && <p className="muted">找不到符合的公開行程資料。</p>}</div>}
    <div className="journey-meta itinerary-metrics" aria-label="每日指標"><span>景點 {metrics.attractions}</span><span>可選 {metrics.optional}</span><span>待補 {metrics.unresolved}</span><span>開車時間 unknown</span><span>步行 unknown</span></div>
    {!showPrintView && <div className="journey-meta quick-mode" aria-label="現場快速模式"><span>現場模式：</span>{(['all', 'now', 'next'] as const).map((mode) => <button key={mode} type="button" className={quickMode === mode ? 'active-pill' : ''} aria-pressed={quickMode === mode} onClick={() => setQuickMode(mode)}>{mode === 'all' ? '全部' : mode}</button>)}<span className="muted">{currentMinutes == null ? '時間或時區不足，now/next 為 unknown' : '依可比較時間顯示'}</span></div>}
    <div className="day"><h3>{selectedDay.date}</h3><p>{selectedDay.summary}</p><ul>{visibleItems.map((item) => { const place = bundle.places?.find((candidate) => candidate.id === item.place_id); const states = itemState(item); return <li className={`journey-item ${item.id === route.item ? 'item-highlight' : ''}`} id={`item-${item.id}`} key={item.id}><div><strong>{item.kind}</strong><span> · {item.start_at || '待補'} ~ {item.end_at || '待補'}</span><div className="status-chips">{states.map((state) => <span key={state} className="status-chip">{state}</span>)}</div></div><div className="journey-meta"><span>地點：{findPlaceLabel(bundle.places, item.place_id)}{place?.name_ja ? ` · ${place.name_ja}` : ''}</span>{findPlaceAddress(bundle.places, item.place_id) && <span>地址：{findPlaceAddress(bundle.places, item.place_id)}</span>}<span>停留：{item.expected_stay_minutes == null ? 'unknown' : `${item.expected_stay_minutes} 分鐘`} · 轉移：{item.transfer_minutes == null ? 'unknown' : `${item.transfer_minutes} 分鐘`} · buffer：{item.buffer_minutes == null ? 'unknown' : `${item.buffer_minutes} 分鐘`}</span>{item.notes && <span>備註：{item.notes}</span>}<a href={buildMapsLink(place?.maps_query || place?.name || item.place_id)} target="_blank" rel="noreferrer">開啟 Google Maps</a>{place?.phone && <a href={`tel:${place.phone}`}>撥打電話</a>}{place?.official_url && <a href={place.official_url} target="_blank" rel="noreferrer">官方網站</a>}<a href={buildRoutePath({ section: 'today', day: selectedDay.date, item: item.id })}>複製路徑</a><button type="button" onClick={() => copyText(`${selectedDay.date}-${item.id}`, `${findPlaceLabel(bundle.places, item.place_id)} ${findPlaceAddress(bundle.places, item.place_id)}`)}>{copiedId === `${selectedDay.date}-${item.id}` ? '已複製' : '複製地址'}</button></div></li> })}</ul></div>
    <section className="workspace-subsection"><h3>Plan A / B / C</h3><div className="journey-meta">{(['A', 'B', 'C'] as const).map((value) => <button key={value} type="button" className={plan === value ? 'active-pill' : ''} onClick={() => setPlan(value)} aria-pressed={plan === value}>Plan {value}</button>)}</div>{alternatives.length ? alternatives.map((alternative) => <article className="journey-item" key={alternative.id}><strong>{alternative.title}</strong><p>{alternative.trigger || '觸發條件待補'} · {alternative.tradeoff || '取捨待補'}</p><p>{alternative.summary || '方案內容待補'} · Decision Gate：{alternative.decision_gate || '待補'}</p></article>) : <p className="muted">Plan {plan} unavailable：目前 public bundle 沒有 validator-approved 備案。</p>}<p className="muted">固定 anchor：{selectedDay.items.filter((item) => item.fixed || item.kind === 'reservation' || item.kind === 'flight').map((item) => item.kind).join('、') || 'unknown'}（方案切換不會修改 Canonical Trip）</p></section>
    {showPrintView && <section className="workspace-subsection print-only"><h3>列印摘要</h3><p>資料版本：{bundle.meta.generated_at} · Critical unknown：{bundle.overview?.critical_unknown_count == null ? 'unknown' : bundle.overview.critical_unknown_count}</p></section>}
  </section>
}
