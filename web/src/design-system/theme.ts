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

const validStatusTones: StatusTone[] = [
  'confirmed',
  'estimated',
  'user-confirmed',
  'official-confirmed',
  'unverified',
  'stale',
  'conflict',
  'error',
  'warning',
  'critical',
  'info',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

export function validateTripThemeContract(value: unknown): value is ThemeCatalog {
  if (!isRecord(value)) return false
  if (!isString(value.version) || !isString(value.defaultThemeId) || !Array.isArray((value as { themes: unknown }).themes)) {
    return false
  }
  const statusAliases = (value as { statusToneAliases?: unknown }).statusToneAliases
  if (statusAliases !== undefined && !isRecord(statusAliases)) return false
  return true
}

export function coerceTheme(
  source: unknown,
  fallback: TripTheme,
): { theme: TripTheme; designTokens?: Partial<DesignTokens> } {
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
        destination: (maybeTheme.brand?.destination as DestinationRole) || fallback.brand.destination,
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
