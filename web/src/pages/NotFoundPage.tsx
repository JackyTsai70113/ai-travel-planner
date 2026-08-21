interface NotFoundPageProps {
  path: string
}

export function NotFoundPage({ path }: NotFoundPageProps) {
  return (
    <section className="card" aria-label="頁面不存在">
      <h2>找不到頁面</h2>
      <p>找不到：{path}</p>
      <p>已自動切到「旅行總覽」。</p>
    </section>
  )
}
