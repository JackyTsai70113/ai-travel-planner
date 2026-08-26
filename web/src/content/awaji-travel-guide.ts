import type { BundleProvenance } from '../contracts/trip'

export interface DailyAlternative {
  title: string
  reasons: [string, string]
}

export interface DailyGuide {
  weather: string
  temperature: string
  rain: string
  heatRisk: string
  wind: string
  activity: string
  steps: string
  stairs: string
  slope: string
  driving: string
  fixedTimes: string
  tide?: string
  rainOptions: DailyAlternative[]
  extraTimeOptions: DailyAlternative[]
  source: BundleProvenance & {
    source_refs?: string[]
    valid_from?: string
    valid_until?: string
    timezone?: string
  }
}

export interface PlaceGuide {
  duration: string
  cost: string
  queue: string
  parking: string
  highlights: string[]
  sourceUrl: string
  hours?: string
  source: BundleProvenance
}

export interface ArrivalParkingGuide {
  text: string
  sourceUrl: string
  source: BundleProvenance
}

export interface TravelAssistantGuide {
  daily_guides: Record<string, DailyGuide>
  arrival_parking: Record<string, ArrivalParkingGuide>
  place_guides: Record<string, PlaceGuide>
}
