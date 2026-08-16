export const destinationRoles = ['sea', 'forest', 'sand', 'night', 'sunset'] as const

export type StatusTone =
  | 'confirmed'
  | 'estimated'
  | 'user-confirmed'
  | 'official-confirmed'
  | 'unverified'
  | 'stale'
  | 'conflict'
  | 'error'
  | 'warning'
  | 'critical'
  | 'info'

export type DestinationRole = (typeof destinationRoles)[number]

export interface ColorRoleTokens {
  background: string
  surface: string
  elevated: string
  text: string
  muted: string
  border: string
  primary: string
  accent: string
  danger: string
  warning: string
  success: string
  info: string
}

export interface TypographyTokens {
  display: string
  title: string
  heading: string
  body: string
  label: string
  caption: string
  mono: string
}

export interface SpacingTokens {
  xs: string
  sm: string
  md: string
  lg: string
  xl: string
  '2xl': string
  container: string
}

export interface RadiusTokens {
  sm: string
  md: string
  lg: string
  full: string
}

export interface ElevationTokens {
  sm: string
  md: string
  lg: string
}

export interface MotionTokens {
  enabled: string
  duration: {
    fast: string
    normal: string
    slow: string
  }
  easing: string
}

export interface DesignTokens {
  breakpoints: {
    xs: number
    sm: number
    md: number
    lg: number
    xl: number
    xxl: number
  }
  colors: ColorRoleTokens
  destination: Record<DestinationRole, string>
  status: Record<StatusTone, { background: string; text: string; border: string; label: string }>
  typography: TypographyTokens
  spacing: SpacingTokens
  radius: RadiusTokens
  elevation: ElevationTokens
  zIndex: {
    modal: number
    popover: number
    overlay: number
    sticky: number
  }
  focus: {
    ring: string
    outline: string
  }
  touchTarget: {
    minHeight: string
    minWidth: string
  }
  print: {
    background: string
    shadow: string
  }
  motion: MotionTokens
}

export const DEFAULT_TAP_TARGET_PX = 44
