import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  clearTripStorage,
  loadTripStorage,
  writeTripStorage,
  type ReadTripStorageOptions,
  type TripStorageReadResult,
} from '../lib/storage/tripStorage'

export interface UseTripStorageOptions<T> extends Omit<ReadTripStorageOptions<T>, 'onCorruptSave'> {
  enabled?: boolean
}

export interface UseTripStorageResult<T> {
  value: T
  setValue: (value: T) => void
  status: TripStorageReadResult<T>['status']
  warning: string | null
  saveError: string | null
  reset: (value: T) => void
  clear: () => void
}

export function useTripStorage<T>(options: UseTripStorageOptions<T>): UseTripStorageResult<T> {
  const {
    tripId,
    module,
    schemaVersion,
    fallback,
    validate,
    legacyKeys = [],
    legacyParser,
    enabled = true,
  } = options

  const [value, setValue] = useState<T>(fallback)
  const [status, setStatus] = useState<TripStorageReadResult<T>['status']>('default')
  const [warning, setWarning] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(() => {
    if (!enabled || !tripId) {
      setValue(fallback)
      setStatus('default')
      setWarning(null)
      setLoaded(true)
      return
    }

    const result = loadTripStorage({
      tripId,
      module,
      schemaVersion,
      fallback,
      validate,
      legacyKeys,
      legacyParser,
    })

    setValue(result.value)
    setStatus(result.status)
    setWarning(result.warning ?? null)
    setLoaded(true)
    setSaveError(null)
  }, [enabled, fallback, legacyKeys, legacyParser, module, schemaVersion, tripId, validate])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!enabled || !tripId || !loaded) {
      return
    }
    const result = writeTripStorage({ tripId, module, schemaVersion, value })
    if (!result.ok) {
      setSaveError(result.error ?? '儲存失敗')
      return
    }
    setSaveError(null)
  }, [enabled, loaded, module, schemaVersion, tripId, value])

  const reset = useCallback(
    (nextValue: T) => {
      setValue(nextValue)
    },
    [],
  )

  const clear = useCallback(() => {
    if (!tripId) {
      return
    }
    clearTripStorage(tripId, module, schemaVersion)
    setValue(fallback)
  }, [tripId, module, schemaVersion, fallback])

  return useMemo(
    () => ({ value, setValue, status, warning, saveError, reset, clear }),
    [clear, reset, saveError, status, value, warning],
  )
}
