import type { MediaAsset } from './ResponsiveImage'
import { ResponsiveImage } from './ResponsiveImage'

export function MediaCard({ asset, title, children }: { asset?: MediaAsset; title: string; children?: React.ReactNode }) {
  return <article className="media-card">
    {asset ? <ResponsiveImage asset={asset} sizes="(min-width: 768px) 33vw, 92vw" /> : <div className="media-card__fallback"><IllustratedFallback label={`${title} 圖像暫不可用`} /></div>}
    <div className="media-card__body"><h3>{title}</h3>{asset?.caption ? <p>{asset.caption}</p> : children}</div>
  </article>
}

function IllustratedFallback({ label }: { label: string }) {
  return <div role="img" aria-label={label}><span aria-hidden="true">◌</span></div>
}
