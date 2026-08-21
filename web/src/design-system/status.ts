export type DataStatusTone =
  | 'confirmed'
  | 'estimated'
  | 'reported'
  | 'user-confirmed'
  | 'warning'
  | 'error'
  | 'critical'
  | 'info'
  | 'unverified'
  | 'stale'
  | 'conflict'

const STATUS_LABELS: Record<DataStatusTone, string> = {
  confirmed: '可執行',
  estimated: '待更新',
  reported: '已回報',
  'user-confirmed': '已確認',
  warning: '待補資訊',
  error: '嚴重訊息',
  critical: '關鍵風險',
  info: '注意',
  unverified: '未驗證',
  stale: '資料過期',
  conflict: '衝突',
}

export const BUNDLE_STATUS_TO_DATA_STATUS = {
  ok: 'confirmed',
  warning: 'warning',
  error: 'error',
} as const

export type BundleStatus = keyof typeof BUNDLE_STATUS_TO_DATA_STATUS

export function bundleStatusTone(status: BundleStatus): DataStatusTone {
  return BUNDLE_STATUS_TO_DATA_STATUS[status] ?? 'unverified'
}

export function statusLabel(status: DataStatusTone): string {
  return STATUS_LABELS[status] ?? STATUS_LABELS.unverified
}
