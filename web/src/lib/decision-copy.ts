const UNKNOWN_MARKER = /(?:尚|仍)?未(?:公布|提供|標示|證實|確認|保證|取得)|未知|待補|以現場(?:資訊|公告|指示)?為準|依當日(?:公告|營運)/

const EMPTY_VALUE = /^(?:依採買內容|依個人需求|彈性安排|無資料)$/
const EMPTY_PREFIX = /^(?:(?:官方|店家|單店頁|設施)?|\d{1,2}:\d{2}\s*後)$/

function cleanSegment(rawSegment: string): string {
  const segment = rawSegment.trim()
  if (!segment) return ''

  const markerIndex = segment.search(UNKNOWN_MARKER)
  if (markerIndex < 0) return segment
  if (markerIndex === 0) return ''

  const prefix = segment.slice(0, markerIndex).trim()
  return EMPTY_PREFIX.test(prefix.replace(/\s+/g, '')) ? '' : prefix
}

function cleanClause(rawClause: string): string {
  const clause = rawClause
    .split(/，|(?<!\d),(?!\d)/)
    .map(cleanSegment)
    .filter(Boolean)
    .join('，')

  const cleaned = clause.replace(/[；。\s]+$/g, '')
  return cleaned && !EMPTY_VALUE.test(cleaned) ? cleaned : ''
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
