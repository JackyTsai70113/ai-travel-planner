import type { TripTheme } from '../design-system/theme'
import { fallbackJapanTheme } from './fallback-japan'
import { genericJapanTheme } from './generic-japan'
import { setouchiAwajiTheme } from './setouchi-awaji'

export const themeCatalog: TripTheme[] = [fallbackJapanTheme, setouchiAwajiTheme, genericJapanTheme]

export const themeById = (id: string): TripTheme => themeCatalog.find((item) => item.id === id) ?? fallbackJapanTheme

export const themeIds = themeCatalog.map((theme) => theme.id)
