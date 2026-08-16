import type { DestinationRole, DesignTokens, StatusTone } from './tokens'

export interface TripTheme {
  id: string
  displayName: string
  description: string
  brand: {
    destination: DestinationRole
    palette: {
      primary: string
      secondary: string
      accent: string
    }
    seasonalMotif?: string
  }
  lightText: boolean
  hero: {
    imageHint?: string
    gradient: string
    pattern?: string
  }
  mapAccent: string
  routeAccent: string
  tokens: {
    colorRoles: string[]
    spacing: string[]
    motion: string
  }
}

export interface TripThemeContract {
  themes: TripTheme[]
  defaultThemeId: string
  statusToneAliases: Partial<Record<string, StatusTone>>
}

export interface ThemeCatalog {
  version: string
  themes: TripTheme[]
  defaultThemeId: string
  statusToneAliases: Partial<Record<string, StatusTone>>
}

export const DEFAULT_STATUS_TONE_ALIASES: Partial<Record<string, StatusTone>> = {
  ok: 'confirmed',
  warning: 'warning',
  error: 'error',
  critical: 'critical',
}

export interface CoercedThemeResult {
  theme: TripTheme
  designTokens?: Partial<DesignTokens>
}

const themeVersionPattern = /^1\.\d+\.\d+$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isDestinationRole(value: unknown): value is DestinationRole {
  return (
    value === 'sea' ||
    value === 'forest' ||
    value === 'sand' ||
    value === 'night' ||
    value === 'sunset'
  )
}

function isStatusTone(value: unknown): value is StatusTone {
  return (
    value === 'confirmed' ||
    value === 'estimated' ||
    value === 'user-confirmed' ||
    value === 'official-confirmed' ||
    value === 'unverified' ||
    value === 'stale' ||
    value === 'conflict' ||
    value === 'error' ||
    value === 'warning' ||
    value === 'critical' ||
    value === 'info'
  )
}

export function validateTripThemeContract(value: unknown): value is ThemeCatalog {
  if (!isRecord(value)) return false
  if (!isString(value.version) || !themeVersionPattern.test(value.version) || !isString(value.defaultThemeId) || !Array.isArray((value as { themes: unknown }).themes)) {
    return false
  }
  if ((value as { themes: unknown[] }).themes.length === 0) return false
  const statusAliases = (value as { statusToneAliases?: unknown }).statusToneAliases
  if (statusAliases !== undefined && !isRecord(statusAliases)) return false
  for (const tone of Object.values(statusAliases || {})) {
    if (!isStatusTone(tone)) return false
  }
  const catalogThemes = (value as { themes: unknown[] }).themes
  const hasMatchingDefaultTheme = catalogThemes.some(
    (item) => isRecord(item) && isString(item.id) && item.id === value.defaultThemeId,
  )
  if (!hasMatchingDefaultTheme) return false
  for (const item of catalogThemes) {
    if (!isRecord(item)) return false
    if (!isString(item.id) || !isString(item.displayName) || !isString(item.description)) return false
    if (!isRecord(item.brand)) return false
    if (!isRecord(item.brand.palette)) return false
    if (!isString((item.brand.palette as { primary?: unknown }).primary)) return false
    if (!isString((item.brand.palette as { secondary?: unknown }).secondary)) return false
    if (!isString((item.brand.palette as { accent?: unknown }).accent)) return false
    if (!isDestinationRole(item.brand.destination)) return false
    if (!isRecord(item.hero)) return false
    if (!isString(item.hero.gradient)) return false
  }
  return true
}

export function coerceTheme(
  source: unknown,
  fallback: TripTheme,
): CoercedThemeResult {
  if (!isRecord(source)) {
    return { theme: fallback }
  }
  const maybeTheme = source as Partial<TripTheme>
  if (!isString(maybeTheme.id)) return { theme: fallback }
  return {
    theme: {
      id: maybeTheme.id,
      displayName: isString(maybeTheme.displayName) ? maybeTheme.displayName : fallback.displayName,
      description: isString(maybeTheme.description) ? maybeTheme.description : fallback.description,
      brand: {
        destination: isDestinationRole(maybeTheme.brand?.destination) ? maybeTheme.brand.destination : fallback.brand.destination,
        palette: {
          primary: isString(maybeTheme.brand?.palette?.primary)
            ? maybeTheme.brand.palette.primary
            : fallback.brand.palette.primary,
          secondary: isString(maybeTheme.brand?.palette?.secondary)
            ? maybeTheme.brand.palette.secondary
            : fallback.brand.palette.secondary,
          accent: isString(maybeTheme.brand?.palette?.accent)
            ? maybeTheme.brand.palette.accent
            : fallback.brand.palette.accent,
        },
        seasonalMotif: maybeTheme.brand?.seasonalMotif || fallback.brand.seasonalMotif,
      },
      lightText: maybeTheme.lightText === undefined ? fallback.lightText : Boolean(maybeTheme.lightText),
      hero: {
        imageHint: maybeTheme.hero?.imageHint || fallback.hero.imageHint,
        gradient: isString(maybeTheme.hero?.gradient) ? maybeTheme.hero.gradient : fallback.hero.gradient,
        pattern: maybeTheme.hero?.pattern || fallback.hero.pattern,
      },
      mapAccent: isString(maybeTheme.mapAccent) ? maybeTheme.mapAccent : fallback.mapAccent,
      routeAccent: isString(maybeTheme.routeAccent) ? maybeTheme.routeAccent : fallback.routeAccent,
      tokens: {
        colorRoles: Array.isArray(maybeTheme.tokens?.colorRoles)
          ? maybeTheme.tokens.colorRoles.filter((item): item is string => isString(item))
          : fallback.tokens.colorRoles,
        spacing: Array.isArray(maybeTheme.tokens?.spacing)
          ? maybeTheme.tokens.spacing.filter((item): item is string => isString(item))
          : fallback.tokens.spacing,
        motion: isString(maybeTheme.tokens?.motion) ? maybeTheme.tokens.motion : fallback.tokens.motion,
      },
    },
  }
}

export function coerceStatusTone(raw: unknown, aliases: Partial<Record<string, StatusTone>> = {}): StatusTone {
  if (isString(raw)) {
    if (isStatusTone(raw)) return raw
    const mapped = aliases[raw]
    if (isStatusTone(mapped)) return mapped
  }
  return 'unverified'
}
