import { GoogleMapsLogo } from './GoogleMapsLogo'

interface MapPinLinkProps {
  href: string
  label: string
  className?: string
}

/** 連到指定地點的 Google Maps，並顯示官方品牌歸屬標示。 */
export function MapPinLink({ href, label, className = '' }: MapPinLinkProps) {
  return <a className={`map-pin-link ${className}`.trim()} href={href} target="_blank" rel="noreferrer" aria-label={label} title={label}>
    <GoogleMapsLogo />
  </a>
}
