import { useState } from 'react'
import type { MediaAsset } from './ResponsiveImage'
import { ResponsiveImage } from './ResponsiveImage'

export function ImageGallery({ assets }: { assets: MediaAsset[] }) {
  const [selected, setSelected] = useState(0)
  if (!assets.length) return null
  return <section aria-label="圖片圖庫">
    <ResponsiveImage asset={assets[selected]} priority sizes="(min-width: 768px) 70vw, 100vw" />
    <div role="tablist" aria-label="選擇圖片">
      {assets.map((asset, index) => <button key={asset.id} type="button" role="tab" aria-selected={index === selected} aria-label={`顯示第 ${index + 1} 張：${asset.alt}`} onClick={() => setSelected(index)}>{index + 1}</button>)}
    </div>
  </section>
}
