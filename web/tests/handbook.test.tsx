import { cleanup, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Bundle } from '../src/contracts/trip'
import type { TripCatalogEntry } from '../src/contracts/trip-registry'
import { buildMapsDirectionsLink } from '../src/lib/google-maps-links'
import { FoodPage } from '../src/pages/FoodPage'
import { heroNextItem, ItineraryPage } from '../src/pages/ItineraryPage'
import { OverviewPage } from '../src/pages/OverviewPage'
import { PackingPage } from '../src/pages/PackingPage'
import { ReservationsPage } from '../src/pages/ReservationsPage'

const dates = ['2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31']
const placeIds = ['ramen-ichiraku-nijigen', 'map-import-yumebutai', 'sumoto-castle', 'uzushio-cruise-fukura', 'kobe-airport-terminal-2']
const placeNames = ['ラーメン一樂', '淡路夢舞台', '洲本城', 'うずしおクルーズ（福良港）', '神戶機場第二航廈']

const bundle: Bundle = {
  trip_id: 'awaji-test',
  title: '2026 瀨戶內五日行',
  status: 'ok',
  local_timezone: 'Asia/Tokyo',
  date_range: { start_date: dates[0], end_date: dates[4] },
  traveler_profile: { adults: 6, children_count: 1, children_ages: [3] },
  selected: { hotel_place_ids: ['awaji-riverside-hotel'], flight_ids: [] },
  places: [
    ...placeIds.map((id, index) => ({ id, name: placeNames[index], maps_query: `${placeNames[index]} 日本` })),
    { id: 'awaji-riverside-hotel', name: 'Awaji Riverside Terrace in Shizuki 780', maps_query: 'Awaji Riverside Terrace in Shizuki 780', official_url: 'https://www.booking.com/' },
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

  it('每日頁面直接顯示天候、負擔、費用與玩法，名稱就是地圖連結', () => {
    render(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[0], raw: `today/${dates[0]}` }} onNavigate={vi.fn()} />)
    expect(screen.getByText('天氣與氣溫')).toBeInTheDocument()
    expect(screen.getByText('降雨')).toBeInTheDocument()
    expect(screen.getByText('中暑與風浪')).toBeInTheDocument()
    expect(screen.getByText('活動量')).toBeInTheDocument()
    expect(screen.getByText('開車時間')).toBeInTheDocument()
    expect(screen.getByText('費用')).toBeInTheDocument()
    expect(screen.getByText('推薦餐點與飲品')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ラーメン一樂 在 Google Maps 開啟' })).toHaveClass('timeline-title-link')
    expect(document.querySelector('.timeline-map-link')).toBeNull()
    expect(document.body.textContent).not.toMatch(/規劃估計|Sheet 指定|家庭／無障礙|聯絡[／/]參考|狀態正常/)
  })

  it('潮流只放在第 3、4 天，並提供官方潮見表', () => {
    const { rerender } = render(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[0], raw: '' }} onNavigate={vi.fn()} />)
    expect(screen.queryByText('鳴門潮流與海況')).not.toBeInTheDocument()
    rerender(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[2], raw: '' }} onNavigate={vi.fn()} />)
    expect(screen.getByText('鳴門潮流與海況')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /查看官方潮見表/ })).toHaveAttribute('href', 'https://www.uzunomichi.jp/tide-calendar/')
    rerender(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[3], raw: '' }} onNavigate={vi.fn()} />)
    expect(screen.getByText(/13:20 南流最快/)).toBeInTheDocument()
  })

  it('每日底部同時提供雨天與額外時間方案，每個方案有兩個理由', () => {
    render(<ItineraryPage bundle={bundle} route={{ section: 'today', day: dates[2], raw: '' }} onNavigate={vi.fn()} />)
    const groups = screen.getByLabelText('雨天與額外時間推薦').querySelectorAll('.day-alternative-group')
    expect(groups).toHaveLength(2)
    groups.forEach((group) => within(group as HTMLElement).getAllByRole('listitem').length >= 2)
  })

  it('總覽使用主行程旅客人數，沒有狀態或資料快照', () => {
    const trip = { title: '淡路五日', destination_regions: ['淡路島'], date_range: { start_date: dates[0], end_date: dates[4] }, duration_days: 5, travelers_summary: '2 位大人', status: 'published', readiness: 'incomplete', cover_media: { kind: 'gradient', gradient: 'linear-gradient(#123, #456)' }, hero_summary: '舊摘要' } as TripCatalogEntry
    render(<OverviewPage bundle={bundle} trip={trip} />)
    expect(screen.getAllByText('6 大 1 小').length).toBeGreaterThan(0)
    expect(document.body.textContent).not.toMatch(/狀態正常|行前需確認|資料快照|舊摘要|Canonical Trip/)
  })

  it('預約頁只保留時間、內容、玩法與文字式地圖連結', () => {
    render(<ReservationsPage bundle={{ ...bundle, reservations: [{ id: 'cruise', day: dates[3], time: `${dates[3]}T12:50:00+09:00`, name: 'うずしおクルーズ（福良港）', place_id: 'uzushio-cruise-fukura', kind: 'fixed-reservation' }] }} />)
    expect(screen.getByText('12:50')).toBeInTheDocument()
    expect(screen.getByText(/成人 ¥3,000/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /うずしおクルーズ（福良港） 在 Google Maps 開啟/ })).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/地址|資料來源|最後確認|fixed-reservation/)
    expect(document.querySelector('svg')).toBeNull()
  })

  it('攜帶物品是完整閱讀清單，不要求旅途中勾選或填寫', () => {
    render(<PackingPage bundle={bundle} />)
    expect(screen.getByText('護照')).toBeInTheDocument()
    expect(screen.getByText('暈船藥或暈車用品')).toBeInTheDocument()
    expect(screen.getByText('日本 eSIM／漫遊方案')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/未完成時|聯絡[／/]參考|離線/)
  })

  it('餐飲頁列出推薦品項、價格與地圖連結', () => {
    render(<FoodPage bundle={bundle} />)
    expect(screen.getByText('一樂拉麵')).toBeInTheDocument()
    expect(screen.getByText(/每人約 ¥1,000–1,800/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /ラーメン一樂 在 Google Maps 開啟/ })).toBeInTheDocument()
  })

  it('行程結束後不把下一站跳回早餐', () => {
    expect(heroNextItem(bundle.days[0], null)?.id).toBe('move-0')
    expect(heroNextItem(bundle.days[0], 23 * 60 + 59)).toBeNull()
  })

})
