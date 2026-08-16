import { Bundle } from '../contracts/trip'

interface HandbookPageProps {
  bundle: Bundle
}

export function HandbookPage({ bundle }: HandbookPageProps) {
  const warningCount = bundle.validation.filter((item) => item.severity === 'warning' || item.severity === 'error').length

  return (
    <section className="card" aria-label="旅行手冊">
      <h2>旅行手冊與緊急資訊</h2>
      <p>硬性提醒項目共 {bundle.preferences.hard_constraints.length} 條</p>
      <ul>
        {bundle.preferences.hard_constraints.map((item) => (
          <li key={item.id}>{item.description}</li>
        ))}
      </ul>
      <h3>系統提醒</h3>
      <p>共 {warningCount} 筆需要關注提醒</p>
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
  )
}
