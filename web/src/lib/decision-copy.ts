const UNKNOWN_MARKER = /(?:尚|仍)?未(?:公布|提供|標示|證實|確認|保證|取得)|未知|待補|以現場(?:資訊|公告|指示)?為準|依當日(?:公告|營運)/

const EMPTY_VALUE = /^(?:依採買內容|依個人需求|彈性安排|無資料)$/

function cleanClause(rawClause: string): string {
  let clause = rawClause.trim()
  if (!clause) return ''

  const markerIndex = clause.search(UNKNOWN_MARKER)
  if (markerIndex === 0 || (markerIndex > 0 && clause.slice(0, markerIndex).replace(/[\s，,]/g, '').match(/^(?:官方|店家|單店頁|設施)?$/))) {
    return ''
  }
  if (markerIndex > 0) {
    const commaIndex = Math.max(clause.lastIndexOf('，', markerIndex), clause.lastIndexOf(',', markerIndex))
    clause = clause.slice(0, commaIndex >= 0 ? commaIndex : markerIndex).trim()
  }

  clause = clause.replace(/[；。\s]+$/g, '')
  return clause && !EMPTY_VALUE.test(clause) ? clause : ''
}

/**
 * 只保留旅客能據以決策的已知資訊。
 * 未知、未公布或把確認責任交回旅客的片段不應出現在介面。
 */
export function decisionCopy(value: string | null | undefined): string | null {
  if (!value) return null
  const clauses = value
    .split(/[；。]+/)
    .map(cleanClause)
    .filter(Boolean)
  return clauses.length > 0 ? clauses.join('；') : null
}
