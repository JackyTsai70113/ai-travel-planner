interface MapPinLinkProps {
  href: string
  label: string
  className?: string
}

/** 使用 Heroicons（MIT）風格的 map pin，並在地圖連結旁顯示 Google Maps attribution。 */
export function MapPinLink({ href, label, className = '' }: MapPinLinkProps) {
  return <a className={`map-pin-link ${className}`.trim()} href={href} target="_blank" rel="noreferrer" aria-label={label} title={label}>
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 21s6-5.2 6-11a6 6 0 1 0-12 0c0 5.8 6 11 6 11Z" />
      <circle cx="12" cy="10" r="2.25" />
    </svg>
    <span aria-hidden="true" translate="no">Google Maps</span>
  </a>
}
