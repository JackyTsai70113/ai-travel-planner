import type { TripTheme } from '../design-system/theme'

export const setouchiAwajiTheme: TripTheme = {
  id: 'setouchi-awaji',
  displayName: '淡路島（關西）',
  description: '以海岸與漁港語彙為核心的視覺語言，配色偏冷、留白較多。',
  brand: {
    destination: 'sea',
    palette: {
      primary: '#0b6da8',
      secondary: '#174a7a',
      accent: '#2bb6d6',
    },
    seasonalMotif: 'marina-breeze',
  },
  lightText: false,
  hero: {
    imageHint: 'setouchi-coastline',
    gradient: 'linear-gradient(135deg, #e3f2fd 0%, #d9f2ff 40%, #f5fbff 100%)',
    pattern: 'waves-outline',
  },
  mapAccent: '#0d47a1',
  routeAccent: '#00897b',
  tokens: {
    colorRoles: ['background', 'surface', 'elevated', 'text', 'muted', 'border', 'primary', 'accent'],
    spacing: ['xs', 'sm', 'md', 'lg', 'xl', '2xl'],
    motion: 'standard',
  },
}
