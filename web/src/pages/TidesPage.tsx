import { Bundle } from '../contracts/trip'
interface TidesPageProps {
  bundle: Bundle
  day?: string
}

function tideLabel(kind: string) {
  if (kind === 'high') return '滿潮'
  if (kind === 'low') return '干潮'
  return `潮汐轉折（${kind}）`
}

export function TidesPage({ bundle, day }: TidesPageProps) {
  const warnings = bundle.validation.filter((item) => item.severity !== 'info')
  const tide = bundle.conditions?.tide
  const tideDays = tide?.days || []
  const selectedDay = tideDays.find((item) => item.date === day) || tideDays[0]
  const hasTideData = Boolean(selectedDay && tideDays.length > 0)

  return (
    <section className="card hub-card-wrapper" aria-label="潮汐與動態條件">
      <header className="hub-header">
        <h2>潮汐與動態條件</h2>
        <p>{tide?.summary || '潮汐資料目前無法顯示。'}</p>
      </header>

      <div className="hub-stats">
        <p>提醒：{warnings.length}</p>
        <p>潮汐資料：{hasTideData ? tide?.status_label || '官方預測' : '—'}</p>
      </div>

      <p className="shell-message">測站：{tide?.station || '洲本（SUMOTO）'}；時間：日本時間</p>

      <section className="hub-section">
        {tideDays.map((item) => (
          <article className={`hub-item${item.date === selectedDay?.date ? ' hub-item-selected' : ''}`} key={item.date}>
            <div className="hub-item-row">
              <span className="hub-status confirmed">{tide?.status_label || '官方預測'}</span>
              <h3>{item.date}{item.date === selectedDay?.date ? '（目前日期）' : ''}</h3>
            </div>
            <p>潮汐型態：{item.tide_type}</p>
            <ul className="hub-alert-list">
              {item.events.map((event) => (
                <li key={`${item.date}-${event.kind}-${event.time}`}>{tideLabel(event.kind)} {event.time}（{event.height_cm} cm）</li>
              ))}
            </ul>
            <p className="hub-meta">潮位為預測值；實際潮位會受氣象與海況影響，海邊活動仍依現場安全狀況調整。</p>
          </article>
        ))}
        {!hasTideData ? <p className="hub-empty">目前沒有可顯示的潮位預測。</p> : null}
      </section>

      {warnings.length > 0 ? (
        <section className="hub-section">
          <h3>相關提醒</h3>
          <ul className="hub-alert-list">
            {warnings.map((item) => (
              <li key={item.code} className="hub-empty">
                [{item.severity}] {item.message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="hub-footer">
        {tide?.source_url ? <a href={tide.source_url} target="_blank" rel="noreferrer">查看官方潮位表</a> : null}
      </p>
    </section>
  )
}
