import { Bundle } from '../contracts/trip'
interface TidesPageProps {
  bundle: Bundle
}

export function TidesPage({ bundle }: TidesPageProps) {
  const warnings = bundle.validation.filter((item) => item.severity !== 'info')
  const days = bundle.days

  return (
    <section className="card hub-card-wrapper" aria-label="潮汐與動態條件">
      <header className="hub-header">
        <h2>潮汐與動態條件</h2>
        <p>目前僅提供行程層級警示；尚未接入潮汐與路況的專屬公域欄位。</p>
      </header>

      <div className="hub-stats">
        <p>提醒：{warnings.length}</p>
        <p>潮汐資料：未提供</p>
      </div>

      <p className="shell-message">資料版本：{bundle.meta.generated_at}</p>

      <section className="hub-section">
        {days.map((day) => (
          <article className="hub-item" key={day.date}>
            <div className="hub-item-row">
              <span className="hub-status unknown">unknown</span>
              <h3>{day.date}</h3>
            </div>
            <p>高低潮資料：未提供（public-bundle）</p>
            <p>可行動窗口：待補</p>
            <p>child / elder 限制：未提供</p>
            <p className="hub-meta">請務必以官方預報與現場公告為準，不做潮汐結果保證。</p>
          </article>
        ))}
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
        目前缺失可再補充欄位：high/low 時刻、運能窗口、交通臨時封閉與天候警示與來源。
      </p>
    </section>
  )
}
