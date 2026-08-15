import { useEffect, useMemo, useState } from 'react'

interface BundleDayItem {
  id: string
  kind: string
  start_at: string | null
  end_at: string | null
  place_id: string
  notes?: string
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
  budget: {
    currency: string
    total: { amount: number; currency: string }
    categories: Record<string, { amount: number; currency: string }>
  }
  validation: { code: string; message: string; severity: string }[]
  meta: {
    generated_at: string
  }
}

function formatMoney(value: { amount: number; currency: string } | null): string {
  if (!value) return '--'
  return `${value.currency} ${value.amount.toLocaleString()}`
}

function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [error, setError] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const urls = [
          `${import.meta.env.BASE_URL}public-bundle.json`,
          '/trips/awaji-2026/public-bundle.json',
          '/public-bundle.json',
        ]
        let response: Response | undefined
        for (const candidate of urls) {
          try {
            const result = await fetch(candidate)
            if (result.ok) {
              response = result
              break
            }
          } catch {
            // continue
          }
        }

        if (!response) {
          throw new Error('public-bundle.json 無法載入')
        }
        const data = await response.json()
        setBundle(data as Bundle)
      } catch (err) {
        setError(err instanceof Error ? err.message : '載入發生未知錯誤')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const totalDays = useMemo(() => bundle?.days.length ?? 0, [bundle])

  if (loading) {
    return <main className="shell">讀取行程中…</main>
  }

  if (error || !bundle) {
    return <main className="shell">{error || '資料異常'}</main>
  }

  const warningCount = bundle.validation.filter((item) => item.severity === 'warning' || item.severity === 'error').length
  const unresolvedReservations = bundle.reservations.filter((reservation) => reservation.unresolved)

  return (
    <main className="shell">
      <header className="hero">
        <p className="eyebrow">Issue 52 · Golden Trip</p>
        <h1>{bundle.title}</h1>
        <p>{bundle.date_range.start_date} ~ {bundle.date_range.end_date}</p>
        <p>時區：{bundle.local_timezone}</p>
        <p>行程狀態：{bundle.status}</p>
      </header>

      <section className="card">
        <h2>旅客與住宿摘要</h2>
        <p>大人人數：{bundle.traveler_profile.adults}</p>
        <p>小孩數：{bundle.traveler_profile.children_count}</p>
        <p>小孩年齡：{bundle.traveler_profile.children_ages.join(', ')}</p>
        <p>已鎖定飯店：{bundle.selected.hotel_place_ids.join('、')}</p>
        <p>已鎖定航班：{bundle.selected.flight_ids.join('、')}</p>
        <p>天數：{totalDays} 天</p>
      </section>

      <section className="card">
        <h2>行程總覽</h2>
        {bundle.days.map((day) => (
          <article key={day.date} className="day">
            <h3>{day.date}</h3>
            <p>{day.summary}</p>
            <ul>
              {day.items.map((item) => (
                <li key={item.id}>
                  <strong>{item.kind}</strong> · {item.start_at ?? '—'} ~ {item.end_at ?? '—'} · {item.place_id}
                  {item.notes ? <span>（{item.notes}）</span> : null}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </section>

      <section className="card">
        <h2>固定預約</h2>
        {bundle.reservations.length ? (
          <ul>
            {bundle.reservations.map((reservation) => (
              <li key={reservation.id}>
                {reservation.day} · {reservation.time} · {reservation.name || '8/28 17:45 固定預約（名稱待補）'}
                {reservation.unresolved ? '（地點與持續時間待補）' : ''}
              </li>
            ))}
          </ul>
        ) : (
          <p>目前無固定預約。</p>
        )}
        {unresolvedReservations.length > 0 ? <p>固定預約資訊待補：地點與持續時間。</p> : null}
        {bundle.meta?.generated_at ? <p>資料產出時間：{bundle.meta.generated_at}</p> : null}
      </section>

      <section className="card">
        <h2>預算</h2>
        <p>總預算：{formatMoney(bundle.budget.total)}</p>
        <dl>
          {Object.entries(bundle.budget.categories).map(([category, amount]) => (
            <div className="budget-row" key={category}>
              <dt>{category}</dt>
              <dd>{formatMoney(amount)}</dd>
            </div>
          ))}
        </dl>
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

      <section className="card">
        <h2>出發前重點提醒</h2>
        <p>景點主軸限定淡路島與鳴門；德島與神戶僅作為住宿、機場與必要交通 anchor。</p>
        <p>行程資料來源為 issue-52 Canonical Trip 與公開-safe bundle，避免在頁面硬寫排程。</p>
      </section>
    </main>
  )
}

export default App
