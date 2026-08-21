import type { CSSProperties, ImgHTMLAttributes } from 'react'

export interface MediaVariant {
  path: string
  width: number
  format: string
}

export interface MediaAsset {
  id: string
  alt: string
  width: number
  height: number
  focalPoint?: { x: number; y: number }
  variants: MediaVariant[]
  fallbackPath?: string
  caption?: string
}

interface Props extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'src' | 'srcSet' | 'alt'> {
  asset: MediaAsset
  priority?: boolean
  sizes?: string
}

export function ResponsiveImage({ asset, priority = false, sizes = '100vw', className, style, ...props }: Props) {
  const variants = asset.variants.filter((variant) => variant.format !== 'svg')
  const src = asset.fallbackPath ?? asset.variants.at(-1)?.path
  const position = asset.focalPoint ? `${asset.focalPoint.x * 100}% ${asset.focalPoint.y * 100}%` : undefined
  if (!src) return <IllustratedFallback label={asset.alt} className={className} />
  return (
    <picture>
      {['avif', 'webp'].map((format) => {
        const formatted = variants.filter((variant) => variant.format === format)
        return formatted.length ? <source key={format} type={`image/${format}`} srcSet={formatted.map((variant) => `${variant.path} ${variant.width}w`).join(', ')} sizes={sizes} /> : null
      })}
      <img
        {...props}
        src={src}
        srcSet={variants.map((variant) => `${variant.path} ${variant.width}w`).join(', ') || undefined}
        sizes={sizes}
        alt={asset.alt}
        width={asset.width}
        height={asset.height}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
        className={className}
        style={{ objectPosition: position, ...style }}
        onError={(event) => {
          event.currentTarget.hidden = true
          event.currentTarget.parentElement?.appendChild(document.createTextNode(asset.alt))
        }}
      />
    </picture>
  )
}

export function IllustratedFallback({ label, className, style }: { label: string; className?: string; style?: CSSProperties }) {
  return <div role="img" aria-label={label} className={className} style={style}><span aria-hidden="true">◌</span><span>{label}</span></div>
}
