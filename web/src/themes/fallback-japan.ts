import type { TripTheme } from '../design-system/theme'

export const fallbackJapanTheme: TripTheme = {
  id: 'fallback-japan',
  displayName: '日本通用 Theme（fallback）',
  description: '未指定主題時的安全預設語意與色票，確保任何行程都能正確顯示',
  brand: {
    destination: 'forest',
    palette: {
      primary: '#1565c0',
      secondary: '#0d47a1',
      accent: '#00acc1',
    },
    seasonalMotif: 'generic-japan',
  },
  lightText: false,
  hero: {
    imageHint: 'japan-landing',
    gradient: 'linear-gradient(135deg, #e8f1ff 0%, #f3f7ff 100%)',
    pattern: 'waves',
  },
  mapAccent: '#1e88e5',
  routeAccent: '#5e35b1',
  tokens: {
    colorRoles: ['background', 'surface', 'elevated', 'text', 'muted', 'border'],
    spacing: ['xs', 'sm', 'md', 'lg', 'xl'],
    motion: 'reduced-motion: active',
  },
}
