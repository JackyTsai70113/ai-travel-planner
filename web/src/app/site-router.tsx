import { useEffect, useMemo, useState } from 'react'
import HomePage from '../pages/HomePage'
import TripApp from './TripApp'
import type { TripCatalogEntry, TripRegistrySections } from '../contracts/trip-registry'
import { buildCatalogSections, isCatalogEntry } from '../contracts/trip-registry'
import { fetchFresh } from '../lib/fresh-fetch'
import { sitePageUrl, siteRootUrl } from './site-links'
export { sitePageUrl, siteRootUrl } from './site-links'

export interface SiteRoute {
  kind: 'home' | 'trip' | 'terms' | 'privacy' | 'not-found'
  slug?: string
}

export function parseSiteRoute(pathname: string): SiteRoute {
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length <= 2 && ['terms', 'terms.html'].includes(segments.at(-1) || '')) return { kind: 'terms' }
  if (segments.length <= 2 && ['privacy', 'privacy.html'].includes(segments.at(-1) || '')) return { kind: 'privacy' }
  const tripsIndex = segments.indexOf('trips')
  if (tripsIndex < 0) return segments.length <= 1 ? { kind: 'home' } : { kind: 'not-found' }
  if (segments.length !== tripsIndex + 2) return { kind: 'not-found' }
  const slug = segments[tripsIndex + 1]
  return slug ? { kind: 'trip', slug } : { kind: 'not-found' }
}

export function siteRootFromPageUrl(pageUrl = window.location.href): URL {
  const url = new URL(pageUrl)
  const segments = url.pathname.split('/').filter(Boolean)
  const tripsIndex = segments.indexOf('trips')
  if (tripsIndex >= 0) {
    url.pathname = `/${segments.slice(0, tripsIndex).join('/')}${segments.slice(0, tripsIndex).length ? '/' : ''}`
  }
  return url
}

export function tripUrl(slug: string, currentUrl = window.location.href): string {
  return new URL(`trips/${encodeURIComponent(slug)}/`, siteRootUrl(currentUrl)).toString()
}

export function setPageMetadata(input: { title: string; description: string; canonical: string }): void {
  document.title = input.title
  const setMeta = (name: string, content: string, property = false) => {
    const selector = property ? `meta[property="${name}"]` : `meta[name="${name}"]`
    let element = document.head.querySelector<HTMLMetaElement>(selector)
    if (!element) {
      element = document.createElement('meta')
      if (property) element.setAttribute('property', name)
      else element.name = name
      document.head.appendChild(element)
    }
    element.content = content
  }
  setMeta('description', input.description)
  setMeta('og:title', input.title, true)
  setMeta('og:description', input.description, true)
  setMeta('og:type', 'website', true)
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'canonical'
    document.head.appendChild(link)
  }
  link.href = input.canonical
}

function RegistryError({ message }: { message: string }) {
  return <main className="portal-state card"><h1>旅行入口暫時無法載入</h1><p>{message}</p></main>
}

function LegalPage({ kind }: { kind: 'terms' | 'privacy' }) {
  const isTerms = kind === 'terms'
  useEffect(() => {
    const title = isTerms ? '使用條款' : '隱私權政策'
    setPageMetadata({
      title: `${title}｜AI Travel Planner`,
      description: isTerms ? 'AI Travel Planner 網站與旅行規劃工具的使用條款。' : 'AI Travel Planner 網站與旅行規劃工具如何處理資料的說明。',
      canonical: sitePageUrl(kind),
    })
  }, [isTerms, kind])

  return (
    <main className="legal-page">
    <header className="legal-header">
        <a href={siteRootUrl().toString()}>AI Travel Planner</a>
        <nav aria-label="法律資訊"><a href={sitePageUrl('terms')}>使用條款</a><a href={sitePageUrl('privacy')}>隱私權政策</a></nav>
      </header>
      {isTerms ? <TermsContent /> : <PrivacyContent />}
      <footer className="legal-footer"><a href={siteRootUrl().toString()}>返回旅行入口</a><span>最後更新：2026 年 10 月 8 日</span></footer>
    </main>
  )
}

function TermsContent() {
  return <article className="legal-content">
    <p className="legal-eyebrow">AI TRAVEL PLANNER</p>
    <h1>使用條款</h1>
    <p>使用本網站、旅行規劃工具或其產生的行程，即表示你已閱讀本條款。若你不同意，請停止使用。</p>
    <h2>服務內容與行程資訊</h2>
    <p>本服務協助整理旅行需求、研究資料並產生行程草案。行程、地點、營業時間、交通、價格與供應情況可能不完整或變動；除非內容明確標示為已確認，否則不得視為訂位、購票、付款或供應商承諾。出發或交易前，請向航空公司、住宿、景點及交通業者確認最新資訊。</p>
    <h2>第三方服務</h2>
    <p>本服務可能連結或使用第三方服務及資料，包括 Google Maps Platform、GitHub Pages、Railway、OpenRouteService、YouTube 與 ChatGPT。這些服務各自受其條款及隱私權政策約束。使用 ChatGPT 時，另適用 <a href="https://openai.com/policies/terms-of-use/" target="_blank" rel="noreferrer">OpenAI 使用條款</a>與<a href="https://openai.com/policies/privacy-policy/" target="_blank" rel="noreferrer">OpenAI 隱私權政策</a>。公開行程頁可能在你瀏覽時向本服務及 Google 即時查詢已排入行程的地點名稱；每次查詢會使用 Google Maps Platform，可能產生 API 費用。Google 查詢失敗時，頁面會標示名稱暫時無法載入。本服務包含 Google Maps 功能與內容；使用這些功能與內容時，亦受當時有效的 <a href="https://maps.google.com/help/terms_maps/" target="_blank" rel="noreferrer">Google Maps／Google Earth 使用者附加條款</a>及<a href="https://policies.google.com/privacy" target="_blank" rel="noreferrer">Google 隱私權政策</a>約束。服務營運亦須遵守<a href="https://cloud.google.com/maps-platform/terms" target="_blank" rel="noreferrer">Google Maps Platform 服務條款</a>。</p>
    <h2>公開分享</h2>
    <p>只有在使用者明確確認公開發布後，行程才會透過 GitHub Pages 公開。公開內容可能被搜尋引擎索引、下載或轉載；請勿在行程需求或公開內容中放入護照、付款資料、精確住址或其他不適合公開的個人資料。</p>
    <h2>合理使用</h2>
    <p>你不得利用本服務從事違法行為、侵犯他人權利、干擾服務運作，或違反第三方服務條款。你對自己提交的資料及公開分享範圍負責。</p>
    <h2>服務變更與責任</h2>
    <p>本服務按現況提供，可能因資料來源、供應商或系統狀態而中斷或更正。法律允許範圍內，本服務不保證旅程資訊完整、即時、無錯誤或適合特定目的；任何旅遊決策仍由使用者自行確認。</p>
    <h2>條款更新與聯絡</h2>
    <p>本條款可能隨服務或適用要求更新，更新版本會刊載於本頁。關於本條款的問題，可透過 <a href="https://github.com/JackyTsai70113/ai-travel-planner/issues" target="_blank" rel="noreferrer">專案 GitHub Issues</a>聯絡維護者；請勿在公開 issue 留下個人或旅行敏感資料。</p>
    <p className="legal-source-note">Google Maps Platform 使用仍須符合其現行<a href="https://developers.google.com/maps/documentation/places/web-service/policies" target="_blank" rel="noreferrer">Places API 政策與歸屬標示規範</a>及<a href="https://cloud.google.com/maps-platform/terms/maps-service-terms" target="_blank" rel="noreferrer">服務專屬條款</a>。</p>
  </article>
}

function PrivacyContent() {
  return <article className="legal-content">
    <p className="legal-eyebrow">AI TRAVEL PLANNER</p>
    <h1>隱私權政策</h1>
    <p>本政策說明 AI Travel Planner 網站與旅行規劃工具在提供服務時處理哪些資料，以及資料會如何使用。最後更新：2026 年 10 月 8 日。</p>
    <h2>處理的資料</h2>
    <p>你提供的旅行需求可能包含目的地、日期、出發地、旅客人數、兒童年齡、預算、交通與偏好。使用規劃工具後，行程草案及研究結果會以行程識別碼儲存在服務後端，供後續讀取、驗證、建置網站及你明確要求的發布功能使用。請只提供完成規劃所需的資訊。</p>
    <h2>資料用途與服務供應商</h2>
    <p>你透過 ChatGPT 送出的訊息先由 OpenAI 處理，再由你呼叫的工具把所需參數傳給本服務；OpenAI 對聊天資料的處理適用其<a href="https://openai.com/policies/privacy-policy/" target="_blank" rel="noreferrer">隱私權政策</a>。本服務收到的旅行需求用於解析、搜尋旅行地點、計算路線、產生及驗證行程。使用 Google Maps Platform 功能時，相關地點搜尋詞及規劃所需的位置資料會傳送給 Google；Google 可能依其政策處理搜尋詞、IP 位址與經緯度等資料。直接開啟 Google Maps 連結時，瀏覽器也會連線至 Google。路線計算資料可能傳送給 OpenRouteService；可選的社群影片搜尋可能使用 YouTube Data API。請參閱 <a href="https://policies.google.com/privacy" target="_blank" rel="noreferrer">Google 隱私權政策</a>、<a href="https://www.openrouteservice.org/terms-of-service/" target="_blank" rel="noreferrer">OpenRouteService 條款</a>及 <a href="https://www.youtube.com/t/terms" target="_blank" rel="noreferrer">YouTube 服務條款</a>。</p>
    <h2>公開行程</h2>
    <p>已確認發布的行程資料會存放在公開 GitHub Pages 網站所使用的 GitHub repository，任何人都可能檢視、複製或由搜尋引擎索引。未公開發布的行程仍可能保存在受認證保護的後端持久化儲存中。不要輸入不希望由服務處理或公開的資料。</p>
    <h2>保存與刪除</h2>
    <p>新建立的行程會保存使用者的行程安排與筆記，以及 Google Places Place ID；Google Places 名稱、地址、座標、營業時間、評分等詳細資料不寫入行程檔或公開靜態頁。公開頁載入當前區段時，會將已排入行程的 Place ID 傳到本服務，再即時向 Google 查詢必要的地點名稱與署名；回應使用 no-store，僅在當前頁面記憶體中用來顯示，不存入瀏覽器儲存空間。查詢失敗時會標示名稱暫時無法載入，不會沿用持久化的 Google 詳細資料。Google Places 座標若在單次請求中使用，請求結束即丟棄，最長保存期限為零天；Google 條款允許的座標快取上限為 30 個連續日。2026 年 10 月 8 日前建立的歷史行程與公開頁面不會因這項變更自動改寫或刪除。GitHub、Railway 或網路服務商可能依其自身政策保留安全、存取及部署紀錄；詳見 <a href="https://developers.google.com/maps/documentation/places/web-service/policies" target="_blank" rel="noreferrer">Places API 政策</a>及<a href="https://cloud.google.com/maps-platform/terms/maps-service-terms" target="_blank" rel="noreferrer">Maps Service Specific Terms</a>。</p>
    <h2>Cookie 與分析</h2>
    <p>目前網站程式未設定追蹤 Cookie 或第三方分析工具。網站主機與服務供應商可能依其政策處理必要的連線及安全紀錄。</p>
    <h2>你的選擇與聯絡</h2>
    <p>你可以不提交旅行資料，也可以要求維護者更正或刪除可識別的行程資料。請透過 <a href="https://github.com/JackyTsai70113/ai-travel-planner/issues" target="_blank" rel="noreferrer">專案 GitHub Issues</a>聯絡維護者；該處是公開討論區，請勿附上私人資訊，並以行程識別碼描述請求。</p>
    <p className="legal-source-note">本頁提供服務資料處理說明；第三方服務可能依其自己的政策收集資料。若本政策與第三方服務條款不同，使用其服務時仍須遵守第三方條款。</p>
  </article>
}

export default function SiteRouter() {
  const route = useMemo(() => parseSiteRoute(window.location.pathname), [])
  const [catalog, setCatalog] = useState<TripCatalogEntry[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (route.kind === 'terms' || route.kind === 'privacy') return
    const registryUrl = new URL('trip-registry.json', siteRootFromPageUrl())
    fetchFresh(registryUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`registry HTTP ${response.status}`)
        return response.json() as Promise<unknown>
      })
      .then((value) => {
        if (!Array.isArray(value) || !value.every(isCatalogEntry)) throw new Error('registry schema 不相容')
        setCatalog(value)
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'registry 載入失敗'))
  }, [route.kind])

  useEffect(() => {
    if (!catalog) return
    const trip = route.slug ? catalog.find((item) => item.slug === route.slug) : null
    if (route.kind === 'home') {
      setPageMetadata({
        title: 'AI Travel Planner｜日本旅行網站入口',
        description: '探索由主行程資料產生、清楚整理每日玩法與實用資訊的日本旅行網站。',
        canonical: siteRootUrl().toString(),
      })
    } else if (trip) {
      setPageMetadata({
        title: `${trip.title}｜AI Travel Planner`,
        description: trip.hero_summary,
        canonical: tripUrl(trip.slug),
      })
    }
  }, [catalog, route.kind, route.slug])

  if (route.kind === 'terms' || route.kind === 'privacy') return <LegalPage kind={route.kind} />
  if (error) return <RegistryError message={error} />
  if (!catalog) return <main className="portal-state card"><h1>AI Travel Planner</h1><p>正在載入旅行入口…</p></main>

  if (route.kind === 'not-found') return <RegistryError message="找不到這個旅程頁面，請回到入口重新選擇。" />

  if (route.kind === 'trip') {
    const trip = catalog.find((item) => item.slug === route.slug)
    if (!trip) return <RegistryError message="找不到這趟旅行，請從入口重新選擇。" />
    return <TripApp tripMeta={trip} tripSlug={trip.slug} />
  }

  const sections: TripRegistrySections = buildCatalogSections(catalog)
  return (
    <HomePage
      catalog={catalog}
      sections={sections}
      setRoute={({ slug }) => { if (slug) window.location.assign(tripUrl(slug)) }}
      searchPlaceholder="搜尋目的地、旅程或標籤"
    />
  )
}
