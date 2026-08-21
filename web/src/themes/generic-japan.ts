import type { TripTheme } from '../design-system/theme'

export const genericJapanTheme: TripTheme = {
  id: 'generic-japan',
  displayName: 'Generic Japan',
  description: '不綁定特定城市的泛日本主題，可直接套用到各個行程。',
  brand: {
    destination: 'sand',
    palette: {
      primary: '#8d4e2f',
      secondary: '#3d2c52',
      accent: '#d97706',
    },
    seasonalMotif: 'temple-shadow',
  },
  lightText: false,
  hero: {
    imageHint: 'tokyo-rail',
    gradient: 'linear-gradient(140deg, #fff8e1 0%, #ffecb3 30%, #fef3c7 100%)',
    pattern: 'origami-paper',
  },
  mapAccent: '#ef6c00',
  routeAccent: '#7e57c2',
  tokens: {
    colorRoles: ['background', 'surface', 'elevated', 'text', 'muted', 'border', 'primary', 'accent', 'danger'],
    spacing: ['xs', 'sm', 'md', 'lg', 'xl'],
    motion: 'standard',
  },
}
