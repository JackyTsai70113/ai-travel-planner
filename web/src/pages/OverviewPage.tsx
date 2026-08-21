import {
  Bundle,
  formatMoney,
} from '../contracts/trip'

interface OverviewPageProps {
  bundle: Bundle
}

export function OverviewPage({ bundle }: OverviewPageProps) {
  return (
    <section className="card" aria-label="旅行總覽">
      <h2>旅行總覽</h2>
      <p className="muted">{bundle.title}</p>
      <div className="grid two-col">
        <p>時區：{bundle.local_timezone}</p>
        <p>行程天數：{bundle.days.length} 天</p>
        <p>大人人數：{bundle.traveler_profile.adults}</p>
        <p>小孩：{bundle.traveler_profile.children_count}</p>
        <p>小孩年齡：{bundle.traveler_profile.children_ages.join(', ') || '未提供'}</p>
        <p>住宿：{bundle.selected.hotel_place_ids.join('、') || '待補'}</p>
      </div>
      <div className="notes">
        <h3>行程固定資源</h3>
        <p>航班：{bundle.selected.flight_ids.join('、') || '待補'}</p>
        <p>資料最後更新：{bundle.meta.generated_at}</p>
      </div>
      <p className="muted">總預算：{formatMoney(bundle.budget.total)}</p>
    </section>
  )
}
