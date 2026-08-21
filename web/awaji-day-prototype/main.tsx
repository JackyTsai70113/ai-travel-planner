import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type BundleItem = { id: string; kind: string; notes?: string | null; place_id: string; start_at: string; end_at: string }
type BundlePlace = { id: string; name: string; address?: string; maps_query?: string }
type BundleDay = { date: string; summary: string; items: BundleItem[] }
type PublicBundle = { days: BundleDay[]; places: BundlePlace[]; reservations?: Array<{ id: string; name: string; unresolved?: boolean }> }

const BUNDLE_URL = '../public/trips/awaji-2026/public-bundle.json'
const DAY_DATE = '2026-08-28'

const fallbackDay: BundleDay = {
  date: DAY_DATE,
  summary: '淡路北岸與南側移動，預留鳴門固定預約窗',
  items: [
    { id: 'day2-morning-park', kind: 'visit', notes: null, place_id: 'awaji-nakajima-park', start_at: '2026-08-28T09:30:00+09:00', end_at: '2026-08-28T11:00:00+09:00' },
    { id: 'day2-naruto-viewpoint', kind: 'visit', notes: null, place_id: 'naruto-whirlpool-viewpoint', start_at: '2026-08-28T14:30:00+09:00', end_at: '2026-08-28T16:30:00+09:00' },
    { id: 'fixed-2026-08-28-17-45', kind: 'visit', notes: '固定預約：8/28 17:45 しあわせのパンケーキ。地點與持續時間仍待補。', place_id: 'naruto-ferry-fixed-activity', start_at: '2026-08-28T17:45:00+09:00', end_at: '2026-08-28T17:45:00+09:00' },
    { id: 'day2-dinner', kind: 'meal', notes: null, place_id: 'awaji-harbor-diner', start_at: '2026-08-28T19:15:00+09:00', end_at: '2026-08-28T20:30:00+09:00' },
  ],
}

function placeFor(bundle: PublicBundle, id: string): BundlePlace {
  return bundle.places.find((place) => place.id === id) || { id, name: id }
}

function timeOf(value: string): string {
  return new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Tokyo' }).format(new Date(value))
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat('zh-TW', { month: '2-digit', day: '2-digit', weekday: 'short', timeZone: 'Asia/Tokyo' }).format(new Date(`${value}T12:00:00+09:00`))
}

function mapsLink(place: BundlePlace): string {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place.maps_query || place.name)}`
}

function App() {
  const [bundle, setBundle] = useState<PublicBundle | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [copied, setCopied] = useState('')

  useEffect(() => {
    fetch(BUNDLE_URL, { cache: 'no-store' })
      .then((response) => response.ok ? response.json() as Promise<PublicBundle> : Promise.reject(new Error('bundle unavailable')))
      .then(setBundle)
      .catch(() => setLoadError(true))
  }, [])

  const day = useMemo(() => bundle?.days.find((candidate) => candidate.date === DAY_DATE) || fallbackDay, [bundle])
  const places = bundle?.places || []
  const unresolved = bundle?.reservations?.some((reservation) => reservation.id === 'fixed-2026-08-28-17-45' && reservation.unresolved) ?? true

  async function copyPlace(place: BundlePlace) {
    try {
      await navigator.clipboard.writeText(place.name)
      setCopied(place.id)
      window.setTimeout(() => setCopied((current) => current === place.id ? '' : current), 1400)
    } catch {
      setCopied('error')
    }
  }

  return <div className="prototype-app">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">✦</span><span>TRIP PLANNER <small>• 2026</small></span></div>
      <div className="trip-title">2026 淡路島・鳴門<br />家庭旅行</div>
      <div className="trip-meta">08/27–08/31 · 6 大 1 小</div>
      <nav className="side-nav" aria-label="行程導覽">
        <div className="side-nav-label">今日導覽</div>
        <a className="side-link active" href="#itinerary"><span>●</span> 一日行程</a>
        <span className="side-link disabled"><span>○</span> 地圖 / 自駕 <em>Preview</em></span>
        <span className="side-link disabled"><span>○</span> 預約 <em>Preview</em></span>
        <span className="side-link disabled"><span>○</span> 住宿 <em>Preview</em></span>
      </nav>
      <div className="side-alert"><div className="side-nav-label">今日重要提醒</div><strong>17:45 固定預約</strong><span>地點與持續時間待補</span></div>
      <div className="sidebar-foot">Prototype · public bundle data</div>
    </aside>

    <main className="main-content">
      <header className="topbar"><div><span className="mobile-brand">淡路島・鳴門</span><span className="topbar-title">淡路島・鳴門 DAY TRIP</span><span className="topbar-date">{dateLabel(day.date)}</span></div><div className="topbar-right"><span className="status-pill"><span className="status-dot" /> Public data · {loadError ? 'fallback' : 'recorded'}</span><span className="people">6 大 1 小</span><a className="top-action" href="#itinerary">今日路線 <span>↗</span></a></div></header>

      <div className="content-wrap">
        <section className="hero" aria-labelledby="page-title">
          <div className="hero-copy"><p className="eyebrow">DAY 2 · 08/28</p><h1 id="page-title">海岸慢旅與鳴門午後</h1><p className="hero-summary">上午保留淡路島散步，下午前往鳴門，<br className="desktop-only" />17:45 有固定預約，行程需保留緩衝。</p><div className="hero-note"><span>波間行程</span><span>Awaji → Naruto</span></div></div>
          <div className="hero-wave" aria-hidden="true"><span>〰</span><span>〰</span><span>〰</span></div>
          <div className="stats"><div><strong>{day.items.length}</strong><span>主要停靠</span></div><div><strong>17:45</strong><span>固定時間</span></div><div><strong>低～中</strong><span>旅遊節奏</span></div><div className="warning-stat"><strong>1</strong><span>待確認</span></div></div>
        </section>

        <div className="day-tabs" aria-label="行程日期"><button>D1 <span>08/27</span></button><button className="active" aria-current="page">D2 <span>08/28</span></button><button>D3 <span>08/29</span></button><button>D4 <span>08/30</span></button><button>D5 <span>08/31</span></button></div>

        <div className="layout-grid"><section className="itinerary-section" id="itinerary"><div className="section-heading"><div><p className="eyebrow">ITINERARY</p><h2>今日行程</h2></div><span className="summary-chip">{day.summary}</span></div><div className="timeline">{day.items.map((item, index) => { const place = placeFor({ ...bundle, places } as PublicBundle, item.place_id); const fixed = item.id === 'fixed-2026-08-28-17-45'; const meal = item.kind === 'meal'; return <div className={`timeline-item ${fixed ? 'fixed' : meal ? 'meal' : ''}`} key={item.id}><div className="time-col"><strong>{timeOf(item.start_at)}</strong><span>{timeOf(item.end_at) !== timeOf(item.start_at) ? timeOf(item.end_at) : '固定'}</span></div><div className="timeline-rail"><span className="timeline-dot">{fixed ? '◆' : meal ? '✦' : '●'}</span>{index < day.items.length - 1 && <span className="timeline-line" />}</div><article className="stop-card"><div className="stop-topline"><span className="category">{fixed ? '固定預約' : meal ? 'DINNER · 晚餐' : 'ATTRACTION · 景點'}</span>{fixed ? <span className="unresolved-badge">⚠ 待確認</span> : <span className="source-badge">Public bundle</span>}</div><h3>{place.name}</h3>{fixed ? <p className="stop-note warning">名稱已確認；地點與持續時間待補。請保留現場確認空間。</p> : <p className="stop-note">{meal ? '晚間用餐，依當日交通狀況保留彈性。' : index === 0 ? '上午海岸散步，從容展開今日行程。' : '午後前往鳴門，預留固定預約前的移動緩衝。'}</p>}<div className="stop-actions">{!fixed && <a href={mapsLink(place)} target="_blank" rel="noreferrer">⌖ Google Maps</a>}{!fixed && <button type="button" onClick={() => copyPlace(place)}>{copied === place.id ? '✓ 已複製' : '▣ 複製地點'}</button>}{fixed && <span className="action-muted">地點尚未解析</span>}</div></article></div>})}</div></section>
          <aside className="quick-panel"><section className="quick-block reminder"><p className="eyebrow">TODAY'S NOTE</p><h2>今日提醒</h2><div className="reservation-time">17:45 <span>固定預約</span></div><strong>しあわせのパンケーキ</strong><p>名稱已確認</p><div className="pending-line"><span>⚠</span> 地點 / duration 待補</div></section><section className="quick-block lodging"><p className="eyebrow">STAY</p><h2>今日住宿</h2><strong>Awaji Riverside Terrace</strong><p>行程資料已提供名稱；詳細地址與停車資訊未在本 prototype 顯示。</p></section><section className="quick-block actions"><p className="eyebrow">QUICK ACTIONS</p><a href={mapsLink(placeFor({ ...bundle, places } as PublicBundle, day.items[0]?.place_id || ''))} target="_blank" rel="noreferrer">⌖ 開啟今日起點 Maps</a><button type="button" onClick={() => copyPlace({ id: 'day-summary', name: day.summary })}>{copied === 'day-summary' ? '✓ 已複製今日摘要' : '▣ 複製今日摘要'}</button><a href="#page-title">↑ 返回行程頂端</a></section></aside></div>
        <footer className="prototype-footer"><span>Data status: {loadError ? 'fallback content' : '2026-08-28 recorded/public bundle'}</span><span>Prototype preview · 未代表完整 production 功能</span></footer>
      </div>
    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<App />)
