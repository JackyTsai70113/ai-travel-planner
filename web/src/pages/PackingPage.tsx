import { Bundle } from '../contracts/trip'

const PACKING_GROUPS = [
  {
    title: '證件與付款',
    summary: '放在隨身小包，不要放進托運行李。',
    items: [
      ['護照', '每位旅客各自一本；確認效期與姓名和機票一致。'],
      ['台灣駕照、日文譯本與租車資料', '駕駛人集中保管，取用時不必翻大型行李。'],
      ['信用卡 2 張與少量日圓', '不同發卡組織分開放；停車場、小店與寺院可能只收現金。'],
      ['旅遊保險與航班資料', '保單、JX834、JX1835 與住宿訂單保留可直接開啟的電子版。'],
    ],
  },
  {
    title: '高溫、降雨與海風',
    summary: '8 月底白天約 28–34°C，濕度高，午後可能雷雨。',
    items: [
      ['每人 600–1,000 ml 飲水', '車上另放補充水；戶外景點之間直接補充。'],
      ['電解質飲料或補充錠', '忍里、花さじき、洲本城與鳴門公園曝曬較久。'],
      ['寬帽沿帽、太陽眼鏡、SPF50+ 防曬', '海岸與山上遮蔭有限；防曬約每 2–3 小時補擦。'],
      ['輕薄透氣上衣與吸汗內衣', '每人至少多帶 1 套可在車內更換的上衣。'],
      ['折傘或輕量雨衣、防水鞋套', '雷雨時雙手仍可扶幼兒、欄杆或船上扶手。'],
      ['薄外套', '觀潮船、室內冷氣與夜間山頂風大時使用。'],
    ],
  },
  {
    title: '走路與乘船',
    summary: '第 3 天活動量最高，洲本城與眉山有坡道及階梯。',
    items: [
      ['止滑運動鞋', '避免新鞋；船上、石階與雨後步道都需要抓地力。'],
      ['輕量折疊傘車', '確認可快速收折並放入後車廂；另帶防雨罩。'],
      ['暈船藥或暈車用品', '依個人平常使用方式準備；觀潮船約 60 分鐘。'],
      ['小毛巾與備用襪', '流汗、雨淋或乘船後可立即更換。'],
    ],
  },
  {
    title: '幼兒用品',
    summary: '以一天一包的方式分裝，景點間不必重整整個行李箱。',
    items: [
      ['尿布、濕紙巾、隔尿墊與垃圾袋', '每日用量再多帶 2–3 片尿布。'],
      ['替換衣物 2 套與薄外套', '分別放在隨身包與車上備用袋。'],
      ['常吃的點心、水杯與兒童餐具', '排隊、塞車或餐點上桌較慢時可直接使用。'],
      ['防曬、遮陽帽與防蚊液', '確認為幼兒可使用的產品。'],
      ['熟悉的小玩具或安撫物', '長車程與餐廳等待時使用，避免攜帶容易遺失的小零件。'],
    ],
  },
  {
    title: '健康與常用藥',
    summary: '只列會實際用到的品項；個人處方藥依原包裝攜帶。',
    items: [
      ['個人處方藥與用藥清單', '分開放一日份與備用份，標示使用者姓名。'],
      ['退燒止痛、腸胃、過敏與蚊蟲用品', '依平常可安全使用的藥品準備。'],
      ['OK 繃、消毒棉片與水泡貼', '階梯與長時間步行後可立即處理。'],
      ['體溫計與口罩', '旅途中有人不適時能快速判斷狀況。'],
      ['過敏資訊', '食物或藥物過敏者以中、英、日文存在手機。'],
    ],
  },
  {
    title: '手機與充電',
    summary: '手機用於即時導航、查看官方營運資訊與出示電子票券。',
    items: [
      ['手機、充電線與行動電源', '導航、票券與翻譯耗電量高；行動電源隨身攜帶。'],
      ['車用 USB 充電器', '至少提供駕駛導航手機與一台備用手機同時充電。'],
      ['日本 eSIM／漫遊方案', '出發前完成啟用；抵達後直接使用即時導航與官方網站。'],
      ['防水手機袋', '海邊、觀潮船與雷雨時保護手機。'],
    ],
  },
] as const

export function PackingPage({ bundle }: { bundle: Bundle }) {
  return <section className="packing-workspace" aria-label="行前攜帶物品">
    <header className="page-intro packing-intro"><div><p className="eyebrow">行前準備</p><h1>這趟旅程要帶什麼</h1><p>{bundle.traveler_profile.adults} 位大人與 {bundle.traveler_profile.children_count} 位幼兒的五日攜帶清單。這裡只提供出發前閱讀，不要求旅途中勾選或填寫。</p></div></header>
    <div className="packing-guide-grid">{PACKING_GROUPS.map((group) => <section className="packing-guide-card" key={group.title}><header><h2>{group.title}</h2><p>{group.summary}</p></header><ul>{group.items.map(([name, reason]) => <li key={name}><strong>{name}</strong><span>{reason}</span></li>)}</ul></section>)}</div>
    <p className="packing-reference">入境與緊急資訊可直接查看 <a href="https://www.japan.travel/tw/plan/" target="_blank" rel="noreferrer">日本政府觀光局旅遊資訊 ↗</a>。</p>
  </section>
}
