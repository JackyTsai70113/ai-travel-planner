export interface ThemeHero {
  title: string
}

export interface TripTheme {
  id: string
  displayName: string
  attribution: string
  hero: ThemeHero
}

export const genericJapanTheme: TripTheme = {
  id: 'japan-generic',
  displayName: '日本通用主題',
  attribution: '可重用的日本行程排版',
  hero: {
    title: '日本行程導覽',
  },
}

export const fallbackTheme: TripTheme = {
  id: 'fallback-japan',
  displayName: 'Fallback',
  attribution: 'Fallback theme',
  hero: {
    title: '日本行程導覽',
  },
}

export const availableThemes: TripTheme[] = [
  genericJapanTheme,
  fallbackTheme,
]

export function getThemeById(themeId?: string | null): TripTheme {
  return availableThemes.find((theme) => theme.id === themeId) ?? fallbackTheme
}
