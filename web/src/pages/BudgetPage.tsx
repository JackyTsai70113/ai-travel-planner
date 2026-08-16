import { Bundle, formatMoney } from '../contracts/trip'
import { useEffect, useState } from 'react'

const STORAGE_KEYS = {
  budget: 'golden_trip_budget_memo',
}

interface BudgetPageProps {
  bundle: Bundle
}

export function BudgetPage({ bundle }: BudgetPageProps) {
  const [memo, setMemo] = useState('')

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.budget)
      if (saved) {
        const parsed = JSON.parse(saved) as string
        setMemo(parsed)
      }
    } catch {
      setMemo('')
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.budget, JSON.stringify(memo))
  }, [memo])

  const onMemoChange = (next: string) => {
    setMemo(next)
  }

  return (
    <section className="card" aria-label="行李與預算">
      <h2>行李與預算</h2>
      <p>總預算：{formatMoney(bundle.budget.total)}</p>
      <dl>
        {Object.entries(bundle.budget.categories).map(([category, amount]) => (
          <div className="budget-row" key={category}>
            <dt>{category}</dt>
            <dd>{formatMoney(amount)}</dd>
          </div>
        ))}
      </dl>
      <label className="budget-note" htmlFor="budgetMemo">
        出發前預算補充（僅本機儲存）
      </label>
      <textarea
        id="budgetMemo"
        value={memo}
        onChange={(event) => onMemoChange(event.target.value)}
        placeholder="例如：某日臨時超商、收費路線停車補貼"
      />
    </section>
  )
}
