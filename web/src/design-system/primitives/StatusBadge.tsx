import type { StatusTone } from '../tokens'

type StatusBadgeProps = {
  label: string
  tone: StatusTone
  className?: string
}

const toneClass: Record<StatusTone, string> = {
  confirmed: 'trip-status confirmed',
  estimated: 'trip-status estimated',
  'user-confirmed': 'trip-status user-confirmed',
  'official-confirmed': 'trip-status official-confirmed',
  unverified: 'trip-status unverified',
  stale: 'trip-status stale',
  conflict: 'trip-status conflict',
  error: 'trip-status error',
  warning: 'trip-status warning',
  critical: 'trip-status critical',
  info: 'trip-status info',
}

export function StatusBadge(props: StatusBadgeProps): JSX.Element {
  return (
    <span className={`${toneClass[props.tone]} ${props.className || ''}`.trim()} role="status" aria-live="polite">
      {props.label}
    </span>
  )
}
