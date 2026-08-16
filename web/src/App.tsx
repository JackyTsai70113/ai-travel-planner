import { useEffect, useMemo, useState } from 'react'
import { availableThemes, getThemeById } from './contracts/theme'
import { bundleStatusTone, statusLabel, type BundleStatus, type DataStatusTone } from './design-system/status'
import { buildMapsSearchLink, buildRouteDirectionChunks, type MapsStop } from './lib/google-maps-links'

interface BundleDayItem {
  id: string
  kind: string
  start_at: string | null
  end_at: string | null
  place_id: string
  notes?: string
}

interface BundlePlace {
  id: string
  name?: string | null
  address?: string | null
  kind?: string | null
  maps_query?: string | null
}

interface BundleTransportLeg {
  id: string
  mode: string
  status: string
  from_place: string
  to_place: string
  from_label: string
  to_label: string
  departure_at: string | null
  arrival_at: string | null
  note: string | null
  source_refs: string[]
}

interface SearchMatch {
  type: 'place' | 'day-item' | 'reservation'
  id: string
  label: string
  detail?: string
  dayIndex?: number
}

interface BundleDay {
  date: string
  summary: string
  items: BundleDayItem[]
}

interface Constraint {
  id: string
  description: string
}

interface Bundle {
  trip_id: string
  title: string
  status: 'ok' | 'warning' | 'error'
  local_timezone: string
  places?: BundlePlace[]
  date_range: { start_date: string; end_date: string }
  traveler_profile: {
    adults: number
    children_count: number
    children_ages: number[]
  }
  selected: {
    hotel_place_ids: string[]
    flight_ids: string[]
  }
  days: BundleDay[]
  reservations: {
    id: string
    day: string
    time: string | null
    name: string | null
    place_id: string
    kind: string
    unresolved?: boolean
  }[]
  preferences: {
    hard_constraints: Constraint[]
    soft_preferences: Constraint[]
  }
  transport_legs?: BundleTransportLeg[]
  budget: {
    currency: string
    total: { amount: number; currency: string }
    categories: Record<string, { amount: number; currency: string }>
  }
  validation: { code: string; message: string; severity: string }[]
  meta: {
    generated_at: string
    theme_id?: string
  }
}

interface ChecklistState {
  [key: string]: boolean
}

const STORAGE_KEYS = {
  checklist: 'awaji_2026_checklist',
  notes: 'awaji_2026_notes',
  budget: 'awaji_2026_budget',
  theme: 'awaji_2026_theme',
} as const

const DEFAULT_CHECKLIST: ChecklistState = {
  passport: true,
  twn_license: true,
  insurance: false,
  itinerary_print: false,
  cash_change: false,
  child_supplies: false,
  elder_med: false,
  heat_rain: false,
  car_docs: false,
  stroller: false,
  first_aid: false,
}

function safeThemeId(themeId: unknown, fallbackThemeId: string): string {
  if (typeof themeId !== 'string') return fallbackThemeId
  if (!themeId.trim()) return fallbackThemeId
  return getThemeById(themeId).id
}

function safeParseJson<T>(value: string | null, fallback: T): T {
  if (!value) return fallback
  try {
    const parsed = JSON.parse(value)
    return parsed as T
  } catch {
    return fallback
  }
}

function formatMoney(value: { amount: number; currency: string } | null): string {
  if (!value) return '--'
  return `${value.currency} ${value.amount.toLocaleString()}`
}

function findPlaceLabel(places: BundlePlace[] = [], placeId: string): string {
  const found = places.find((place) => place.id === placeId)
  if (!found) return placeId
  return found.name || found.maps_query || placeId
}

function findPlaceAddress(places: BundlePlace[] = [], placeId: string): string {
  const found = places.find((place) => place.id === placeId)
  return found?.address || ''
}

function buildPlaceMapsQuery(places: BundlePlace[] = [], placeId: string): string {
  const found = places.find((place) => place.id === placeId)
  return found?.maps_query || found?.name || placeId
}

function buildTransportRouteHref(leg: BundleTransportLeg): string {
  const chunks = buildRouteDirectionChunks([
    { label: leg.from_label, mapsQuery: leg.from_label } as MapsStop,
    { label: leg.to_label, mapsQuery: leg.to_label } as MapsStop,
  ])
  return chunks[0]?.href || buildMapsSearchLink(`${leg.from_label} 到 ${leg.to_label}`)
}

function containsQuery(value: string | null | undefined, query: string): boolean {
  if (!value) return false
  return value.toLowerCase().includes(query)
}

function toFriendlyStatus(status: Bundle['status']): string {
  if (status === 'ok') return '可執行'
  if (status === 'warning') return '待補資訊'
  return '嚴重訊息'
}

function mapStatusTone(status: Bundle['status']): DataStatusTone {
  return bundleStatusTone(status as BundleStatus)
}

function themeClassName(themeId: string): string {
  return `theme-${themeId}`
}

function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [error, setError] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [activeDay, setActiveDay] = useState(0)
  const [copiedId, setCopiedId] = useState<string>('')
  const [isOnline, setIsOnline] = useState(true)
  const [checklist, setChecklist] = useState<ChecklistState>(DEFAULT_CHECKLIST)
  const [notes, setNotes] = useState<string>('')
  const [tripBudgetMemo, setTripBudgetMemo] = useState<string>('')
  const [themeId, setThemeId] = useState<string>(getThemeById('fallback-japan').id)
  const [searchQuery, setSearchQuery] = useState<string>('')

  useEffect(() => {
    setChecklist(safeParseJson(localStorage.getItem(STORAGE_KEYS.checklist), DEFAULT_CHECKLIST))
    setNotes(safeParseJson(localStorage.getItem(STORAGE_KEYS.notes), ''))
    setTripBudgetMemo(safeParseJson(localStorage.getItem(STORAGE_KEYS.budget), ''))
    setThemeId(
      safeThemeId(
        safeParseJson(localStorage.getItem(STORAGE_KEYS.theme), ''),
        getThemeById('fallback-japan').id,
      ),
    )
    setIsOnline(window.navigator.onLine)

    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.checklist, JSON.stringify(checklist))
  }, [checklist])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.notes, JSON.stringify(notes))
  }, [notes])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.budget, JSON.stringify(tripBudgetMemo))
  }, [tripBudgetMemo])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.theme, JSON.stringify(themeId))
  }, [themeId])

  useEffect(() => {
    const load = async () => {
      const baseUrl = String(import.meta.env.BASE_URL || '/')
      setLoading(true)
      setError('')

      try {
        const urls = [
          `${baseUrl}public-bundle.json`,
          `${baseUrl}trips/awaji-2026/public-bundle.json`,
          './public-bundle.json',
          './trips/awaji-2026/public-bundle.json',
        ]
        const attemptLogs: string[] = []
        let response: Response | null = null

        for (const candidate of urls) {
          try {
            const result = await fetch(candidate)
            if (result.ok) {
              response = result
              break
            }
            attemptLogs.push(`${candidate} => HTTP ${result.status}`)
            continue
          } catch {
            attemptLogs.push(`${candidate} => network error`)
          }
        }

        if (!response) {
          throw new Error(`public-bundle.json 無法載入（已嘗試 ${urls.join('、')}；${attemptLogs.join('；')}）`)
        }
        const data = (await response.json()) as Bundle
        setBundle(data)
        setThemeId((current) => {
          const remoteThemeId = safeThemeId(data.meta?.theme_id, '')
          return remoteThemeId || current
        })
        setActiveDay(0)
      } catch (err) {
        setError(err instanceof Error ? err.message : '載入發生未知錯誤')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [])

  const totalDays = useMemo(() => bundle?.days.length ?? 0, [bundle])
  const selectedTheme = useMemo(() => getThemeById(themeId), [themeId])
  const placeList = useMemo(() => bundle?.places ?? [], [bundle])
  const statusTone = useMemo(() => bundle ? mapStatusTone(bundle.status) : ('unverified' as DataStatusTone), [bundle])
  const warningCount = useMemo(
    () => bundle?.validation.filter((item) => item.severity === 'warning' || item.severity === 'error').length ?? 0,
    [bundle],
  )
  const unresolvedReservations = useMemo(
    () => bundle?.reservations.filter((reservation) => reservation.unresolved) ?? [],
    [bundle],
  )
  const normalizedQuery = useMemo(() => searchQuery.trim().toLowerCase(), [searchQuery])
  const searchMatches = useMemo(() => {
    if (!bundle || !normalizedQuery) return []

    const matches: SearchMatch[] = []
    const placeMatches = new Set<string>()
    const reservationMatches = new Set<string>()
    const dayItemMatches = new Set<string>()

    placeList.forEach((place) => {
      const sourceLabel = place.name || place.maps_query || place.id
      if (
        containsQuery(place.id, normalizedQuery) ||
        containsQuery(sourceLabel, normalizedQuery) ||
        containsQuery(place.address, normalizedQuery) ||
        containsQuery(place.kind, normalizedQuery)
      ) {
        const id = place.id
        if (!placeMatches.has(id)) {
          matches.push({
            type: 'place',
            id,
            label: sourceLabel,
            detail: place.address || undefined,
          })
          placeMatches.add(id)
        }
      }
    })

    bundle.days.forEach((day, index) => {
      day.items.forEach((item) => {
        const placeLabel = findPlaceLabel(placeList, item.place_id)
        const key = `${item.id}-${index}`
        if (
          containsQuery(item.id, normalizedQuery) ||
          containsQuery(item.kind, normalizedQuery) ||
          containsQuery(item.notes, normalizedQuery) ||
          containsQuery(item.start_at, normalizedQuery) ||
          containsQuery(item.end_at, normalizedQuery) ||
          containsQuery(placeLabel, normalizedQuery)
        ) {
          if (!dayItemMatches.has(key)) {
            matches.push({
              type: 'day-item',
              id: key,
              label: `${day.date} ${day.summary}`,
              detail: `${item.kind}｜${placeLabel}`,
              dayIndex: index,
            })
            dayItemMatches.add(key)
          }
        }
      })
    })

    bundle.reservations.forEach((reservation) => {
      const summary = `${reservation.day} ${reservation.time ?? ''} ${reservation.name ?? ''}`.trim()
      if (
        containsQuery(reservation.id, normalizedQuery) ||
        containsQuery(reservation.name, normalizedQuery) ||
        containsQuery(reservation.day, normalizedQuery) ||
        containsQuery(reservation.time, normalizedQuery) ||
        containsQuery(reservation.place_id, normalizedQuery)
      ) {
        if (!reservationMatches.has(reservation.id)) {
          matches.push({
            type: 'reservation',
            id: reservation.id,
            label: summary || reservation.id,
            detail: `${reservation.kind}`,
          })
          reservationMatches.add(reservation.id)
        }
      }
    })

    return matches
  }, [bundle, normalizedQuery, placeList])

  const currentDay = bundle?.days[activeDay] ?? null

  const checklistProgress = useMemo(() => {
    const total = Object.keys(DEFAULT_CHECKLIST).length
    const done = Object.entries(checklist).filter((entry) => entry[1]).length
    return { total, done, rate: total === 0 ? 0 : Math.round((done / total) * 100) }
  }, [checklist])

  const copyText = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(label)
      setTimeout(() => setCopiedId((current) => (current === label ? '' : current)), 1200)
    } catch {
      setError('複製失敗：你的瀏覽器未允許剪貼簿操作')
    }
  }

  if (loading) {
    return <main className="shell">讀取行程中…</main>
  }

  if (error || !bundle) {
    return <main className="shell">{error || '資料異常'}</main>
  }

  return (
      <main className={`shell trip-theme ${themeClassName(selectedTheme.id)}`}>
        <header className="hero">
        <p className="eyebrow">{selectedTheme.hero.title}</p>
        <h1>{bundle.title}</h1>
        <div className="hero-meta">
          <span>{bundle.date_range.start_date} ~ {bundle.date_range.end_date}</span>
          <span className={`status-chip status-${statusTone}`}>{statusLabel(statusTone)}</span>
        </div>
        <p className="hero-subtitle">狀態語意：{statusLabel(statusTone)} · 主題 {selectedTheme.displayName}</p>
        <p className={isOnline ? 'online' : 'offline'}>
          {isOnline ? '已啟用線上版本（會即時更新公有資料快照）' : '目前離線模式：以快取資料顯示'}
        </p>
        <label className="theme-switcher" htmlFor="themeSwitch">
          主題
          <select
            id="themeSwitch"
            value={selectedTheme.id}
            onChange={(event) => setThemeId(event.target.value)}
            aria-label="選擇行程主題"
          >
            {availableThemes.map((theme) => (
              <option key={theme.id} value={theme.id}>
                {theme.displayName}
              </option>
            ))}
          </select>
        </label>
      </header>

      <section className="card">
        <h2>全行程搜尋</h2>
        <input
          id="tripSearch"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="輸入景點、餐飲、住宿、預約、備註"
          aria-label="全行程搜尋"
        />
        {normalizedQuery ? (
          <>
            <p className="muted">共找到 {searchMatches.length} 筆結果</p>
            {searchMatches.length ? (
              <ul>
                {searchMatches.map((match) => (
                  <li className="journey-item" key={`${match.type}-${match.id}`}>
                    <strong>{match.type}</strong>
                    <div className="journey-meta">
                      <span>{match.label}</span>
                      {match.detail ? <span>· {match.detail}</span> : null}
                      {typeof match.dayIndex === 'number' ? (
                        <button type="button" onClick={() => setActiveDay(match.dayIndex as number)}>
                          跳到對應天
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">找不到符合結果</p>
            )}
          </>
        ) : (
          <p className="muted">輸入關鍵字可搜尋景點、日程、預約</p>
        )}
      </section>

      <section className="card">
        <h2>旅程總覽</h2>
        <div className="grid two-col">
          <p>時區：{bundle.local_timezone}</p>
          <p>總天數：{totalDays} 天</p>
          <p>大人人數：{bundle.traveler_profile.adults}</p>
          <p>小孩數：{bundle.traveler_profile.children_count}</p>
          <p>小孩年齡：{bundle.traveler_profile.children_ages.join(', ') || '未提供'}</p>
          <p>固定提醒：{warningCount} 筆</p>
        </div>
        <div className="notes">
          <h3>已鎖定行程基礎</h3>
          <p>住宿：{bundle.selected.hotel_place_ids.join('、') || '待補'}</p>
          <p>航班：{bundle.selected.flight_ids.join('、') || '待補'}</p>
          <p>資料最後更新：{bundle.meta.generated_at}</p>
        </div>
      </section>

      <section className="card">
        <h2>五日行程快速導覽</h2>
        <p className="muted">景點主軸限定淡路島與鳴門，德島、神戶保留住宿與必要交通 anchor。</p>
        <div className="day-tabs" role="tablist" aria-label="行程日程頁籤">
          {bundle.days.map((day, index) => (
            <button
              key={day.date}
              className={`day-tab ${index === activeDay ? 'active' : ''}`}
              role="tab"
              aria-selected={index === activeDay}
              onClick={() => setActiveDay(index)}
              type="button"
            >
              Day {index + 1}
              <span>{day.date}</span>
            </button>
          ))}
        </div>

        {currentDay ? (
          <article className="day">
            <h3>{currentDay.date}</h3>
            <p>{currentDay.summary}</p>
            <ul>
              {currentDay.items.map((item) => (
                <li className="journey-item" key={item.id}>
                  <div>
                    <strong>{item.kind}</strong>
                    <span>
                      {' '}
                      · {item.start_at ?? '—'} ~ {item.end_at ?? '—'}
                    </span>
                  </div>
                  <div className="journey-meta">
                    <span>地點: {findPlaceLabel(placeList, item.place_id)}</span>
                    {findPlaceAddress(placeList, item.place_id) ? (
                      <span>地址: {findPlaceAddress(placeList, item.place_id)}</span>
                    ) : null}
                    {item.notes ? <span>備註: {item.notes}</span> : null}
                    <a
                      href={buildMapsSearchLink(buildPlaceMapsQuery(placeList, item.place_id))}
                      target="_blank"
                      rel="noreferrer"
                    >
                      開啟 Google Maps
                    </a>
                    <button
                      type="button"
                      onClick={() => copyText(`${currentDay.date}-${item.id}`, findPlaceLabel(placeList, item.place_id))}
                      aria-label={`複製地點：${findPlaceLabel(placeList, item.place_id)}`}
                    >
                      {copiedId === `${currentDay.date}-${item.id}` ? '已複製' : '複製地點'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </article>
        ) : null}
      </section>

      <section className="card">
        <h2>日常路線</h2>
        {bundle.transport_legs?.length ? (
          <ul>
            {bundle.transport_legs.map((leg) => (
              <li className="journey-item" key={leg.id}>
                <div>
                  <strong>{leg.mode === 'car' ? '開車' : '行程'}</strong>
                  <span> · 狀態：{leg.status}</span>
                </div>
                <div className="journey-meta">
                  <span>從：{leg.from_label}</span>
                  <span>到：{leg.to_label}</span>
                  <span>
                    時間：{leg.departure_at ?? '待補'} ~ {leg.arrival_at ?? '待補'}
                  </span>
                  <a
                    href={buildTransportRouteHref(leg)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    開啟 Google Maps 路線
                  </a>
                  {leg.note ? <span>備註：{leg.note}</span> : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p>目前無路線資料，請使用地點名稱自行搜尋。</p>
        )}
      </section>

      <section className="card">
        <h2>固定預約</h2>
        {bundle.reservations.length ? (
          <ul>
            {bundle.reservations.map((reservation) => (
              <li key={reservation.id}>
                <span>
                  {reservation.day} · {reservation.time ?? '待補'} · {reservation.name || '8/28 17:45 固定預約（名稱待補）'}
                </span>
                <button
                  type="button"
                  onClick={() => copyText(reservation.id, `${reservation.day} ${reservation.time ?? ''} ${reservation.name ?? ''}`.trim())}
                  aria-label={`複製預約：${reservation.id}`}
                >
                  {copiedId === reservation.id ? '已複製' : '複製預約'}
                </button>
                {reservation.unresolved ? '（地點與持續時間待補）' : ''}
              </li>
            ))}
          </ul>
        ) : (
          <p>目前無固定預約。</p>
        )}
        {unresolvedReservations.length > 0 ? <p>固定預約資訊待補：地點與持續時間。</p> : null}
      </section>

      <section className="card">
        <h2>預算與重點提醒</h2>
        <p>總預算：{formatMoney(bundle.budget.total)}</p>
        <p className="muted">主題備註：{selectedTheme.attribution}</p>
        <dl>
          {Object.entries(bundle.budget.categories).map(([category, amount]) => (
            <div className="budget-row" key={category}>
              <dt>{category}</dt>
              <dd>{formatMoney(amount)}</dd>
            </div>
          ))}
        </dl>
        <label className="budget-note" htmlFor="budgetMemo">出發前預算補充（僅本機儲存）</label>
            <textarea
              id="budgetMemo"
              value={tripBudgetMemo}
              onChange={(event) => setTripBudgetMemo(event.target.value)}
              placeholder="例如：某日臨時超商、收費路線停車補貼"
              aria-label="出發前預算補充"
            />
      </section>

      <section className="card">
        <h2>行李與備忘（本機保存）</h2>
        <div className="muted">完成率：{checklistProgress.done}/{checklistProgress.total}（{checklistProgress.rate}%）</div>
        <ul className="checklist">
          {Object.entries(checklist).map(([key, checked]) => (
            <li key={key}>
              <label>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))}
                />
                {key === 'passport'
                  ? '護照/身分文件'
                  : key === 'twn_license'
                  ? '台灣駕照與國際駕照文件'
                  : key === 'insurance'
                  ? '汽車險與 rental 文件'
                  : key === 'itinerary_print'
                  ? '行程頁列印檔'
                  : key === 'cash_change'
                  ? '零用金與零錢'
                  : key === 'child_supplies'
                  ? '嬰幼兒用品/奶瓶'
                  : key === 'elder_med'
                  ? '長輩基本藥物與緊急連絡'
                  : key === 'heat_rain'
                  ? '防曬與防暑／雨具'
                  : key === 'car_docs'
                  ? '汽車文件與接送人聯絡方式'
                  : '急救用品'}
              </label>
            </li>
          ))}
        </ul>
        <label className="budget-note" htmlFor="tripNotes">臨時備註</label>
        <textarea
          id="tripNotes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="例如：8/28 前往鳴門前是否遇到塞車，或替代店家安排"
          aria-label="臨時備註"
        />
      </section>

      <section className="card">
        <h2>偏好與提醒</h2>
        <h3>硬限制</h3>
        <ul>
          {bundle.preferences.hard_constraints.map((item) => (
            <li key={item.id}>{item.description}</li>
          ))}
        </ul>
        <h3>提醒 ({warningCount})</h3>
        {bundle.validation.length ? (
          <ul>
            {bundle.validation.map((item) => (
              <li key={item.code}>{item.message}</li>
            ))}
          </ul>
        ) : (
          <p>目前無未確定提醒。</p>
        )}
      </section>
    </main>
  )
}

export default App
