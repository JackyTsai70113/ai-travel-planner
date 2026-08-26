import { cleanup, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Bundle } from '../src/contracts/trip'
import type { TripCatalogEntry } from '../src/contracts/trip-registry'
import { decisionCopy } from '../src/lib/decision-copy'
import { buildMapsDirectionsLink, buildRouteDirectionChunks, googleMapsQueryForPlace } from '../src/lib/google-maps-links'
import { usableOfficialHref } from '../src/lib/official-links'
import { FoodPage } from '../src/pages/FoodPage'
import { heroNextItem, ItineraryPage } from '../src/pages/ItineraryPage'
import { OverviewPage } from '../src/pages/OverviewPage'
import { PackingPage } from '../src/pages/PackingPage'
import { ReservationsPage } from '../src/pages/ReservationsPage'

const dates = ['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31']
const placeIds = ['ramen-ichiraku-nijigen', 'map-import-yumebutai', 'sumoto-castle', 'uzushio-cruise-fukura', 'kobe-airport-terminal-2']
const placeNames = ['ラーメン一樂', '淡路夢舞台', '洲本城', 'うずしおクルーズ（福良港）', '神戶機場第二航廈']
const guideSource = { provider: '官方網站', source_url: 'https://www.uzunomichi.jp/', retrieved_at: '2026-08-26T10:30:00+08:00', status: 'reported' as const }
const dailyGuides = Object.fromEntries(dates.map((date, index) => [date, {
  weather: '多雲', temperature: '25–33°C', rain: '降雨機率 35%｜雨量約 2.4 mm', heatRisk: '中暑風險高', wind: '風速約 11 km/h', activity: '中等', steps: '約 5,000 步', stairs: '約 80 階', slope: '有少量坡道', driving: '約 4 小時', fixedTimes: '12:50 觀潮船',
  ...(index === 2 ? { tide: '鳴門海峽 12:40 南流最快' } : index === 3 ? { tide: '鳴門海峽 13:20 南流最快' } : {}),
  rainOptions: [{ title: '室內方案', reasons: ['減少淋雨', '保留主要體驗'] }],
  extraTimeOptions: [{ title: '鄰近景點', reasons: ['不增加車程', '停留時間容易控制'] }],
  source: { ...guideSource, valid_from: `${date}T00:00:00+09:00`, valid_until: `${date}T23:59:59+09:00`, timezone: 'Asia/Tokyo' },
}])) as NonNullable<Bundle['travel_assistant']>['daily_guides']

const placeGuides = {
  'ramen-ichiraku-nijigen': { duration: '45 分鐘', cost: '每人約 ¥1,000–1,800', queue: '官方未公布等候時間；午餐前預留 30 分鐘點餐。', parking: 'E 停車場 477 台免費，步行約 5 分鐘。', parkingMapsQuery: '兵庫県立淡路島公園 E駐車場', highlights: ['一樂拉麵：可從三種湯頭選擇，最能呼應作品設定。', '主題餐點：角色造型讓用餐本身也成為體驗。', '限定飲品：適合想收藏紀念杯的旅客。'], sourceUrl: 'https://elb.nijigennomori.com/food/ichiraku/', hours: '11:00–18:00', source: guideSource },
  'uzushio-cruise-fukura': { duration: '60 分鐘', cost: '成人 ¥3,000', queue: '12:50 船班需提早完成報到與登船。', parking: '道之驛福良周邊免費停車場。', highlights: ['近看漩渦：能從船上近距離觀察潮流變化。', '穿越橋下：可從海面觀看大鳴門橋結構。', '甲板海景：航程中能同時欣賞鳴門海峽。'], sourceUrl: 'https://www.uzu-shio.com/timetable', hours: '12:50 船班', source: guideSource },
} as NonNullable<Bundle['travel_assistant']>['place_guides']

const bundle: Bundle = {
  trip_id: 'awaji-test',
  title: '2026 淡路島五日行',
  status: 'ok',
  local_timezone: 'Asia/Tokyo',
  date_range: { start_date: dates[0], end_date: dates[4] },
  traveler_profile: { adults: 6, children_count: 1, children_ages: [3] },
  selected: { hotel_place_ids: ['awaji-riverside-hotel'], flight_ids: [] },
  places: [
    ...placeIds.map((id, index) => ({ id, name: placeNames[index], maps_query: `${placeNames[index]} 日本`, google_maps_url: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(placeNames[index])}`, ...(index === 0 ? { image_url: 'https://example.com/ramen.jpg', image_source_url: 'https://example.com/official', image_alt: '一樂拉麵' } : {}) })),
    { id: 'awaji-riverside-hotel', name: 'Awaji Riverside Terrace in Shizuki 780', maps_query: '兵庫県淡路市志筑字黒田780-12', google_maps_url: 'https://www.google.com/maps/search/?api=1&query=Awaji+Riverside+Terrace+Shizuki+780-12', official_url: 'https://www.booking.com/', image_url: 'https://example.com/hotel.jpg', image_source_url: 'https://example.com/hotel', image_alt: '住宿外觀' },
  ],
  days: dates.map((date, index) => ({
    date,
    summary: `第 ${index + 1} 日摘要`,
    items: [
      {
        id: `move-${index}`,
        kind: 'transport',
        start_at: `${date}T10:00:00+09:00`,
        end_at: `${date}T10:45:00+09:00`,
        place_id: placeIds[index],
        transport_leg_id: `leg-${index}`,
      },
      {
        id: `visit-${index}`,
        kind: index === 0 || index === 3 ? 'meal' : 'place',
        start_at: `${date}T10:45:00+09:00`,
        end_at: `${date}T12:15:00+09:00`,
        place_id: placeIds[index],
        expected_stay_minutes: 90,
      },
      ...(index === 0 ? [{ id: 'check-in', kind: 'check_in', start_at: `${date}T21:00:00+09:00`, end_at: `${date}T21:20:00+09:00`, place_id: 'awaji-riverside-hotel' }] : []),
    ],
  })),
  transport_legs: dates.map((date, index) => ({
    id: `leg-${index}`,
    mode: 'car',
    status: 'estimated',
    from_place: index === 0 ? 'kobe-airport-terminal-2' : placeIds[index - 1],
    to_place: placeIds[index],
    from_label: index === 0 ? '神戶機場第二航廈' : placeNames[index - 1],
    to_label: placeNames[index],
    departure_at: `${date}T10:00:00+09:00`,
    arrival_at: `${date}T10:45:00+09:00`,
    estimated_duration_minutes: 40,
    transfer_minutes: 45,
    buffer_minutes: 5,
  })),
  operations: { pretrip_checklist: [] },
  travel_assistant: { daily_guides: dailyGuides, arrival_parking: {}, place_guides: placeGuides },
  reservations: [],
  preferences: { hard_constraints: [], soft_preferences: [] },
  budget: { currency: 'JPY', total: { amount: 0, currency: 'JPY' }, categories: {} },
  validation: [],
  meta: { generated_at: '2026-08-26T00:00:00Z' },
}

describe('淡路島只讀旅遊助手', () => {
  beforeEach(() => cleanup())

  it('建立不需要 API key 的 Google Maps 路線', () => {
    const url = new URL(buildMapsDirectionsLink([{ label: '神戶機場' }, { label: '淡路夢舞台' }]))
    expect(url.pathname).toBe('/maps/dir/')
    expect(url.searchParams.get('api')).toBe('1')
    expect(url.searchParams.get('travelmode')).toBe('driving')
  })

  it('多停靠點會分段且每一站都保留在 Google Maps 路線', () => {
    const stops = Array.from({ length: 13 }, (_, index) => ({ id: `stop-${index}`, label: `停靠點 ${index + 1}`, mapsQuery: `日本測試地址 ${index + 1}` }))
    const chunks = buildRouteDirectionChunks(stops)
    const flattenedIds = chunks.flatMap((chunk, index) => [
      ...(index === 0 ? [chunk.source.id] : []),
      ...chunk.waypoints.map((stop) => stop.id),
      chunk.destination.id,
    ])
    expect(flattenedIds).toEqual(stops.map((stop) => stop.id))
    expect(chunks.length).toBeGreaterThan(1)
    chunks.forEach((chunk) => expect(chunk.href).toContain('maps/dir/'))
  })

  it('路線優先使用已驗證的 Google Maps 查詢詞，不回退到無法解析的地址', () => {
    expect(googleMapsQueryForPlace(bundle.places?.find((place) => place.id === 'awaji-riverside-hotel'))).toBe('Awaji Riverside Terrace Shizuki 780-12')
  })

  it('已知資訊後的未知尾句會移除，整段未知時不顯示', () => {
    expect(decisionCopy('GARB COSTA ORANGE 專用停車場 80 台免費；同一 Frogs FARM 三處停車場合計約 300 台免費，官方未公布各場滿位順序。')).toBe('GARB COSTA ORANGE 專用停車場 80 台免費；同一 Frogs FARM 三處停車場合計約 300 台免費')
    expect(decisionCopy('官方未公布分時人流。')).toBeNull()
  })

  it('已失效的舊官方網址會改用已驗證的官方直達頁', () => {
    expect(usableOfficialHref('https://elb.nijigennomori.com/food/ichiraku/')).toBe('https://nijigennomori.com/food/ichiraku/')
    expect(usableOfficialHref('https://awaji-kanransya.com/')).toBe('https://www.jb-highway.co.jp/sapa/awaji_down.html')
  })

  it('每日頁面以名稱連官方網站、map pin 連地圖，並省略未知與重複資訊', () => {
    render(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[0], raw: `today/${dates[0]}` }} onNavigate={vi.fn()} />)
    expect(screen.getByText('天氣與氣溫')).toBeInTheDocument()
    expect(screen.getByText('降雨')).toBeInTheDocument()
    expect(screen.getByText('中暑與風浪')).toBeInTheDocument()
    expect(screen.getByText('活動量')).toBeInTheDocument()
    expect(screen.getByText('開車時間')).toBeInTheDocument()
    expect(screen.getByText('預估花費')).toBeInTheDocument()
    expect(screen.getByText('推薦餐點與飲品')).toBeInTheDocument()
    expect(screen.getByText(/可從三種湯頭選擇/)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'ラーメン一樂' }).some((link) => link.getAttribute('href') === 'https://nijigennomori.com/food/ichiraku/')).toBe(true)
    expect(screen.getByRole('link', { name: /在 Google Maps 開啟 ラーメン一樂.*停車場/ })).toHaveAttribute('href', expect.stringContaining('maps/search'))
    expect(screen.getByText('午餐前預留 30 分鐘點餐')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/官方未公布|未提供|未知/)
    expect(document.querySelector('.arrival-parking')).toBeNull()
    expect(document.querySelector('.parking-map-link')).toBeNull()
    expect(document.querySelector('.official-info-link')).toBeNull()
    expect(document.querySelector('.day-lodging-card')).toBeNull()
    expect(screen.getByTitle(`${dates[0]} 自駕路線圖`)).toHaveAttribute('src', expect.stringContaining('output=embed'))
    expect(screen.getAllByRole('link', { name: /開啟路線/ }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('圖片來源').length).toBeGreaterThan(0)
    expect(document.body.textContent).not.toContain('↗')
    expect(document.querySelector('.timeline-map-link')).toBeNull()
    expect(document.body.textContent).not.toMatch(/規劃估計|Sheet 指定|家庭／無障礙|聯絡[／/]參考|狀態正常|住宿安排已放入今日時間軸/)
  })

  it('潮流只放在第 3、4 天，並提供官方潮見表', () => {
    const { rerender } = render(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[0], raw: '' }} onNavigate={vi.fn()} />)
    expect(screen.queryByText('鳴門潮流與海況')).not.toBeInTheDocument()
    rerender(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[2], raw: '' }} onNavigate={vi.fn()} />)
    expect(screen.getByText('鳴門潮流與海況')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /官方潮見表/ })).toHaveAttribute('href', 'https://www.uzunomichi.jp/tide-calendar/')
    rerender(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[3], raw: '' }} onNavigate={vi.fn()} />)
    expect(screen.getByText(/13:20 南流最快/)).toBeInTheDocument()
  })

  it('每日底部同時提供雨天與額外時間方案，每個方案有兩個理由', () => {
    render(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[2], raw: '' }} onNavigate={vi.fn()} />)
    const groups = screen.getByLabelText('雨天與額外時間推薦').querySelectorAll('.day-alternative-group')
    expect(groups).toHaveLength(2)
    groups.forEach((group) => within(group as HTMLElement).getAllByRole('listitem').length >= 2)
  })

  it('總覽不重複旅客人數、狀態或資料快照', () => {
    const trip = { title: '關西五日', destination_regions: ['大阪', '京都'], date_range: { start_date: dates[0], end_date: dates[4] }, duration_days: 5, travelers_summary: '2 位大人', status: 'published', readiness: 'incomplete', cover_media: { kind: 'gradient', gradient: 'linear-gradient(#123, #456)' }, hero_summary: '關西行程摘要' } as TripCatalogEntry
    render(<OverviewPage bundle={bundle} trip={trip} />)
    expect(document.body.textContent).not.toContain('6 大 1 小')
    expect(document.querySelector('.hero-actions')).toBeNull()
    expect(screen.getByLabelText(/五日移動路線/)).toBeInTheDocument()
    expect(screen.getByText('大阪旅行')).toBeInTheDocument()
    expect(screen.getByText('關西行程摘要')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('淡路島自駕旅行')
    expect(document.body.textContent).not.toMatch(/狀態正常|行前需確認|資料快照|Canonical Trip/)
  })

  it('預約頁名稱連官方網站，map pin 連 Google Maps', () => {
    render(<ReservationsPage bundle={{ ...bundle, reservations: [{ id: 'cruise', day: dates[3], time: `${dates[3]}T12:50:00+09:00`, name: 'うずしおクルーズ（福良港）', place_id: 'uzushio-cruise-fukura', kind: 'fixed-reservation' }] }} />)
    expect(screen.getByText('12:50')).toBeInTheDocument()
    expect(screen.getByText(/成人 ¥3,000/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'うずしおクルーズ（福良港）' })).toHaveAttribute('href', 'https://www.uzu-shio.com/timetable')
    expect(screen.getByRole('link', { name: /在 Google Maps 開啟 うずしおクルーズ/ })).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/地址|資料來源|最後確認|fixed-reservation/)
    expect(document.querySelectorAll('.map-pin-link svg')).toHaveLength(1)
  })

  it('攜帶物品是完整閱讀清單，不要求旅途中勾選或填寫', () => {
    render(<PackingPage bundle={bundle} />)
    expect(screen.getByText('護照')).toBeInTheDocument()
    expect(screen.getByText('暈船藥或暈車用品')).toBeInTheDocument()
    expect(screen.getByText('日本 eSIM／漫遊方案')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/未完成時|聯絡[／/]參考|離線|只提供出發前閱讀|不要求旅途中/)
  })

  it('餐飲頁列出推薦品項，名稱連官方網站且 map pin 連停車場', () => {
    render(<FoodPage bundle={bundle} />)
    expect(screen.getByText('一樂拉麵')).toBeInTheDocument()
    expect(screen.getByText(/每人約 ¥1,000–1,800/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ラーメン一樂' })).toHaveAttribute('href', 'https://nijigennomori.com/food/ichiraku/')
    expect(screen.getByRole('link', { name: /在 Google Maps 開啟 ラーメン一樂.*停車場/ })).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/官方未公布|官方網站/)
  })

  it('行程結束後不把下一站跳回早餐', () => {
    expect(heroNextItem(bundle.days[0], null)?.id).toBe('move-0')
    expect(heroNextItem(bundle.days[0], 23 * 60 + 59)).toBeNull()
  })

})
