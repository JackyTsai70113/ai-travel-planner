export type HandbookCategory = 'driving' | 'lodging' | 'dining' | 'family' | 'weather' | 'shopping' | 'emergency'

export interface HandbookEntry {
  id: string
  category: HandbookCategory
  title: string
  summary: string
  details: string[]
  sourceType: 'curated' | 'official'
  source?: string
  freshness?: string
}

export const HANDBOOK_CATEGORIES: Record<HandbookCategory, string> = {
  driving: '自駕與交通', lodging: '住宿', dining: '餐廳', family: '長輩與幼兒',
  weather: '天候與船班', shopping: '購物與補給', emergency: '緊急資訊',
}

export const HANDBOOK_ENTRIES: HandbookEntry[] = [
  { id: 'drive-basics', category: 'driving', title: '日本自駕基本操作', summary: '靠左行駛，出發前確認駕照、租車文件與導航設定。', details: ['駕駛座與車流方向和台灣不同，轉彎及進出停車場放慢速度。', '導航目的地優先使用地址、電話或 Mapcode，並在停車後再操作手機。'], sourceType: 'curated' },
  { id: 'parking-mapcode', category: 'driving', title: '停車、Mapcode、電話導航', summary: '將停車場入口與目的地分開確認。', details: ['景點名稱可能有多個入口；出發前確認停車場名稱、入口與步行路線。', 'Mapcode 或電話導航是租車機常見輸入方式，請以當次租車機介面為準。'], sourceType: 'curated' },
  { id: 'etc-fuel-return', category: 'driving', title: 'ETC、收費道路、加油與還車', summary: '保留收據，還車前確認油量與營業時間。', details: ['收費道路可能有現金、信用卡或 ETC 不同車道，依現場標誌選擇。', '加油前確認油種；滿油還車與異地還車規則以租車公司合約為準。'], sourceType: 'curated' },
  { id: 'hotel-arrival', category: 'lodging', title: '飯店入住、寄放行李、晚到', summary: '提前聯絡晚到，確認寄放與入住時間。', details: ['保留住宿地址、電話與預約姓名的日文版本。', '晚到、幼兒用品與行李寄放規則各住宿不同，請以住宿方回覆為準。'], sourceType: 'curated' },
  { id: 'restaurant-family', category: 'dining', title: '餐廳、七人座位與兒童椅', summary: '訂位時說明人數、幼兒與兒童椅需求。', details: ['七人座位與兒童椅可能需要事前預約，抵達前再次確認。', '過敏與食材問題要直接向餐廳確認，不以菜名推定成分。'], sourceType: 'curated' },
  { id: 'weather-disruption', category: 'weather', title: '雨天、酷暑、颱風與道路中斷', summary: '動態條件改變時，以官方公告與現場指示為準。', details: ['攜帶飲水、防曬、雨具；高溫時安排室內休息並觀察長輩與幼兒狀況。', '船班、道路與景點營運是動態資訊，出發前及當日重新確認。'], sourceType: 'official', source: '日本政府觀光局（JNTO）與各交通營運方公告', freshness: '動態資訊：出發前及當日重查' },
  { id: 'shopping-taxfree', category: 'shopping', title: '購物、免稅與補給', summary: '免稅資格與文件由店家依現行規定處理。', details: ['購買前詢問免稅櫃檯、護照要求與封裝規則；不要把一般店家說明當成法律意見。', '長途自駕前補充飲水、尿布、零食與常用用品。'], sourceType: 'curated' },
  { id: 'emergency-numbers', category: 'emergency', title: '緊急電話與官方求助', summary: '警察 110；火災、救護車 119。', details: ['通報時說明位置、事件、傷者人數；需要時請住宿方或現場人員協助。', '日本觀光局旅客熱線：JNTO Visitor Hotline（官方網站提供最新語言與服務資訊）。'], sourceType: 'official', source: '日本警察廳、消防廳、JNTO', freshness: '電話號碼穩定；服務語言與連結請出發前重查' },
  { id: 'family-care', category: 'family', title: '長輩與幼兒應變', summary: '以休息、補水、保暖及及早求助為原則。', details: ['暈車、暈船或不適時先安全停靠、休息與補水；持續或嚴重症狀請撥 119 或詢問醫療人員。', '本頁是旅行應變與求助導引，不提供診斷、處方或個別醫療判斷。'], sourceType: 'curated' },
]
