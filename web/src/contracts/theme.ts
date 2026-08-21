export interface ThemeHero {
  title: string
}

export interface TripTheme {
  id: string
  displayName: string
  attribution: string
  hero: ThemeHero
}

export const setouchiAwajiTheme: TripTheme = {
  id: 'setouchi-awaji',
  displayName: 'Setouchi Awaji',
  attribution: '淡路島航程主題',
  hero: {
    title: '淡路島・鳴門行程',
  },
}

export const genericJapanTheme: TripTheme = {
  id: 'japan-generic',
  displayName: '日本通用主題',
  attribution: '淡路島與鳴門綜合排版',
  hero: {
    title: '日本行程導覽',
  },
}

export const fallbackTheme: TripTheme = {
  id: 'fallback-japan',
  displayName: 'Fallback',
  attribution: 'Fallback theme',
  hero: {
    title: '淡路島・鳴門家庭旅行',
  },
}

export const availableThemes: TripTheme[] = [
  setouchiAwajiTheme,
  genericJapanTheme,
  fallbackTheme,
]

export function getThemeById(themeId?: string | null): TripTheme {
  return availableThemes.find((theme) => theme.id === themeId) ?? fallbackTheme
}
