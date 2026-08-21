export interface Attribution {
  id: string
  creator: string
  license: string
  sourceUrl?: string
}

export function AttributionLink({ attribution }: { attribution: Attribution }) {
  const label = `${attribution.creator} · ${attribution.license}`
  return attribution.sourceUrl ? <a href={attribution.sourceUrl} target="_blank" rel="noreferrer" aria-label={`圖片來源：${label}`}>{label}</a> : <span aria-label={`圖片來源：${label}`}>{label}</span>
}
