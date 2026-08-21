import { Bundle } from '../contracts/trip'

interface SourcesPageProps {
  bundle: Bundle
}

export function SourcesPage({ bundle }: SourcesPageProps) {
  return (
    <section className="card" aria-label="資料來源">
      <h2>資料來源與更新狀態</h2>
      <p>tripId：{bundle.trip_id}</p>
      <p>快照時間：{bundle.meta.generated_at}</p>
      <p>最後更新訊息：資料源由公共資料流程輸出，頁面版本不保證即時。</p>
    </section>
  )
}
