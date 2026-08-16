export interface VersionedStorageEnvelope<T> {
  schemaVersion: number
  tripId: string
  updatedAt: string
  data: T
}

export interface TripStorageReadResult<T> {
  value: T
  status: 'ok' | 'default' | 'migrated' | 'corrupt'
  warning?: string
}

export interface TripStorageWriteResult {
  ok: boolean
  error?: string
}

export interface ReadTripStorageOptions<T> {
  tripId: string
  module: 'checklist' | 'budget' | 'notes' | 'preferences'
  schemaVersion: number
  fallback: T
  validate: (value: unknown) => value is T
  legacyKeys?: string[]
  legacyParser?: (raw: string) => T | null
  onCorruptSave?: (corruptKey: string, raw: string) => void
}

export interface WriteTripStorageOptions<T> {
  tripId: string
  module: 'checklist' | 'budget' | 'notes' | 'preferences'
  schemaVersion: number
  value: T
}

export const DEFAULT_TRIP_ID = 'awaji-2026'

export function mkTripStorageKey(tripId: string, module: string, version: number): string {
  return `trip:${tripId}:${module}:v${version}`
}

function parseJson<T>(raw: string): { ok: true; value: T } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(raw) as T }
  } catch {
    return { ok: false }
  }
}

function isEnvelope<T>(value: unknown): value is VersionedStorageEnvelope<T> {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as VersionedStorageEnvelope<T>).schemaVersion === 'number' &&
    typeof (value as VersionedStorageEnvelope<T>).tripId === 'string' &&
    typeof (value as VersionedStorageEnvelope<T>).updatedAt === 'string' &&
    Object.prototype.hasOwnProperty.call((value as VersionedStorageEnvelope<T>), 'data')
  )
}

export function moveCorruptedTripStorageKey(moduleKey: string, raw: string): void {
  const corruptedKey = `${moduleKey}:corrupt`
  try {
    localStorage.setItem(corruptedKey, raw)
  } catch {
    // no-op if storage quota or storage unavailable
  }
}

export function loadTripStorage<T>(options: ReadTripStorageOptions<T>): TripStorageReadResult<T> {
  const {
    tripId,
    module,
    schemaVersion,
    fallback,
    validate,
    legacyKeys = [],
    legacyParser,
    onCorruptSave,
  } = options

  const targetKey = mkTripStorageKey(tripId, module, schemaVersion)
  const rawValue = localStorage.getItem(targetKey)

  if (rawValue) {
    const parsed = parseJson<unknown>(rawValue)
    if (!parsed.ok) {
      moveCorruptedTripStorageKey(targetKey, rawValue)
      onCorruptSave?.(targetKey, rawValue)
      return {
        value: fallback,
        status: 'corrupt',
        warning: `${module} 儲存資料格式錯誤，已保留原始內容於 ${targetKey}:corrupt，已回復預設。`,
      }
    }

    if (isEnvelope<T>(parsed.value)) {
      const envelope = parsed.value
      if (envelope.schemaVersion === schemaVersion && envelope.tripId === tripId && validate(envelope.data)) {
        return { value: envelope.data, status: 'ok' }
      }
    }

    if (typeof parsed.value !== 'string' && validate(parsed.value as T)) {
      return { value: parsed.value as T, status: 'ok' }
    }

    return {
      value: fallback,
      status: 'corrupt',
      warning: `${module} 儲存資料內容非預期格式，已回復預設。`,
    }
  }

  for (const legacyKey of legacyKeys) {
    const legacyRaw = localStorage.getItem(legacyKey)
    if (!legacyRaw) {
      continue
    }

    let parsedLegacy: T | null

    if (legacyParser) {
      parsedLegacy = legacyParser(legacyRaw)
    } else {
      const parsed = parseJson<T>(legacyRaw)
      parsedLegacy = parsed.ok && validate(parsed.value) ? parsed.value : null
    }

    if (parsedLegacy) {
      try {
        localStorage.setItem(
          targetKey,
          JSON.stringify({
            schemaVersion,
            tripId,
            updatedAt: new Date().toISOString(),
            data: parsedLegacy,
          } as VersionedStorageEnvelope<T>),
        )
      } catch {
        // best effort only
      }
      return {
        value: parsedLegacy,
        status: 'migrated',
        warning: `${module} 套用了舊版 ${legacyKey} 後台資料並已完成 trip key migration。`,
      }
    }

    moveCorruptedTripStorageKey(legacyKey, legacyRaw)
  }

  return {
    value: fallback,
    status: 'default',
  }
}

export function writeTripStorage<T>(options: WriteTripStorageOptions<T>): TripStorageWriteResult {
  const { tripId, module, schemaVersion, value } = options
  const targetKey = mkTripStorageKey(tripId, module, schemaVersion)
  const envelope: VersionedStorageEnvelope<T> = {
    schemaVersion,
    tripId,
    updatedAt: new Date().toISOString(),
    data: value,
  }

  try {
    localStorage.setItem(targetKey, JSON.stringify(envelope))
    return { ok: true }
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'QuotaExceededError') {
      return { ok: false, error: `${module} 儲存超過配額，請清理 localStorage 或刪除不必要資料後重試。` }
    }
    return { ok: false, error: `${module} 儲存失敗：${error instanceof Error ? error.message : '未知錯誤'}` }
  }
}

export function clearTripStorage(tripId: string, module: string, schemaVersion: number): void {
  try {
    localStorage.removeItem(mkTripStorageKey(tripId, module, schemaVersion))
    localStorage.removeItem(`${mkTripStorageKey(tripId, module, schemaVersion)}:corrupt`)
  } catch {
    // no-op
  }
}
