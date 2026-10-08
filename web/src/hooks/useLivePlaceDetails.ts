import { useEffect, useMemo, useRef, useState } from 'react'
import { Bundle, BundlePlace } from '../contracts/trip'
import { SectionId } from '../app/route-registry'

interface PlaceDetails {
  name: string
  attribution: string
  thirdPartyAttributions: Array<{ provider?: string; providerUri?: string }>
}

export function scheduledPlaceIdsForSection(bundle: Bundle, section: SectionId, activeDate?: string): string[] {
  const scheduledIds = new Set<string>()
  const add = (id: string | undefined) => {
    if (id) scheduledIds.add(id)
  }
  if (section === 'today') {
    const day = bundle.days.find((entry) => entry.date === activeDate) || bundle.days[0]
    day?.items.forEach((item) => add(item.place_id))
  } else if (section === 'overview') {
    for (const day of bundle.days) {
      add(day.items[0]?.place_id)
      add(day.items.at(-1)?.place_id)
    }
  } else if (section === 'food') {
    for (const day of bundle.days) {
      for (const item of day.items) if (item.kind === 'meal' || item.kind === 'food') add(item.place_id)
    }
  } else if (section === 'reservation') {
    bundle.reservations.forEach((reservation) => add(reservation.place_id))
  }

  return [...scheduledIds].filter((id) => {
    const place = bundle.places?.find((entry) => entry.id === id)
    return !!place?.google_place_id && !place.name
  })
}

export function useLivePlaceDetails(bundle: Bundle | null, tripSlug: string | undefined, section: SectionId, activeDate?: string) {
  const [details, setDetails] = useState<Record<string, PlaceDetails | null>>({})
  const inFlight = useRef(new Set<string>())
  const ids = useMemo(
    () => bundle ? scheduledPlaceIdsForSection(bundle, section, activeDate) : [],
    [activeDate, bundle, section],
  )
  const idKey = ids.join('\u0000')
  const baseUrl = bundle?.place_details_api_base_url?.replace(/\/$/, '')

  useEffect(() => {
    if (!baseUrl || !tripSlug || !idKey) return
    const pending = idKey.split('\u0000').filter((id) => !(id in details) && !inFlight.current.has(id))
    if (!pending.length) return
    pending.forEach((id) => inFlight.current.add(id))

    void Promise.all(pending.map(async (id) => {
      try {
        const place = bundle?.places?.find((entry) => entry.id === id)
        if (!place?.google_place_id) return [id, null] as const
        const endpoint = `${baseUrl}/${encodeURIComponent(tripSlug)}/places/${encodeURIComponent(place.google_place_id)}`
        const response = await fetch(endpoint, { method: 'GET', cache: 'no-store', credentials: 'omit' })
        if (!response.ok) return [id, null] as const
        const value = await response.json() as Record<string, unknown>
        if (value.status !== 'available' || typeof value.name !== 'string' || typeof value.attribution !== 'string') {
          return [id, null] as const
        }
        const thirdPartyAttributions = Array.isArray(value.third_party_attributions)
          ? value.third_party_attributions.flatMap((item) => {
            if (!item || typeof item !== 'object' || Array.isArray(item)) return []
            const candidate = item as Record<string, unknown>
            return [{
              provider: typeof candidate.provider === 'string' ? candidate.provider : undefined,
              providerUri: typeof candidate.providerUri === 'string' ? candidate.providerUri : undefined,
            }]
          })
          : []
        return [id, { name: value.name, attribution: value.attribution, thirdPartyAttributions }] as const
      } catch {
        return [id, null] as const
      }
    })).then((results) => {
      pending.forEach((id) => inFlight.current.delete(id))
      setDetails((current) => {
        const next = { ...current }
        for (const [id, value] of results) next[id] = value
        return next
      })
    }).catch(() => {
      pending.forEach((id) => inFlight.current.delete(id))
    })
  }, [baseUrl, bundle, details, idKey, tripSlug])

  const displayBundle = useMemo(() => {
    if (!bundle) return null
    const pendingIds = new Set(ids)
    const places = bundle.places?.map((place): BundlePlace => {
      if (!place.google_place_id || place.name) return place
      const result = details[place.id]
      if (result) {
        return {
          ...place,
          name: result.name,
          place_details_attribution: result.attribution,
          place_details_third_party_attributions: result.thirdPartyAttributions,
        }
      }
      if (place.id in details) return { ...place, place_details_state: 'unavailable' }
      if (pendingIds.has(place.id)) return { ...place, place_details_state: 'loading' }
      return place
    })
    return { ...bundle, places }
  }, [bundle, details, ids])

  return { bundle: displayBundle, lookupEnabled: !!baseUrl }
}
