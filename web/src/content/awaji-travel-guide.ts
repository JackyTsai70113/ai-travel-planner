export interface DailyAlternative {
  title: string
  reasons: [string, string]
}

export interface DailyGuide {
  weather: string
  temperature: string
  rain: string
  heatRisk: string
  wind: string
  activity: string
  steps: string
  stairs: string
  slope: string
  driving: string
  fixedTimes: string
  tide?: string
  rainOptions: DailyAlternative[]
  extraTimeOptions: DailyAlternative[]
}

export interface PlaceGuide {
  duration: string
  cost: string
  queue: string
  parking: string
  highlights: string[]
  sourceUrl: string
  hours?: string
}

export const AWAJI_DAILY_GUIDE: Record<string, DailyGuide> = {
  '2026-08-27': {
    weather: '多雲、上午可能有雷雨，午後仍可能有短暫雨',
    temperature: '27–33°C',
    rain: '降雨機率 29%｜雨量約 0.1 mm',
    heatRisk: '中暑風險高：忍里與海岸行程曝曬時間長',
    wind: '最大風速約 25 km/h；海邊風感明顯',
    activity: '中高',
    steps: '約 6,000–8,000 步',
    stairs: '約 60–120 階',
    slope: '忍里有坡道與不平整路面',
    driving: '約 3 小時 35 分',
    fixedTimes: '10:30 JX834 抵達｜18:30 GARB 晚餐',
    rainOptions: [
      { title: '縮短忍里，改逛二次元之森室內商店與餐飲區', reasons: ['仍保留 NARUTO 主題體驗', '不必增加跨區車程'] },
      { title: '取消海岸散步，提早到 GARB COSTA ORANGE', reasons: ['避免雷雨與強風曝露', '可保留晚餐前休息時間'] },
    ],
    extraTimeOptions: [
      { title: '兵庫縣立淡路島公園展望區', reasons: ['與忍里同園區，不必另找停車位', '可看明石海峽與園區景觀'] },
    ],
  },
  '2026-08-28': {
    weather: '陰天，午後有雨',
    temperature: '25–30°C',
    rain: '降雨機率 65%｜雨量約 17.7 mm',
    heatRisk: '中暑風險中等：濕度高，體感仍悶熱',
    wind: '最大風速約 21 km/h',
    activity: '高',
    steps: '約 7,000–9,000 步',
    stairs: '約 150–250 階',
    slope: '夢舞台、百段苑與水御堂有階梯',
    driving: '約 5 小時',
    fixedTimes: '13:00 鯛料理午餐｜17:45 幸福鬆餅',
    rainOptions: [
      { title: '以淡路夢舞台室內空間與安藤建築動線為主', reasons: ['地下停車場可直接進入建築群', '可避開花田長時間淋雨'] },
      { title: '花さじき改為 HELLO KITTY SMILE', reasons: ['主要展區在室內', '同在淡路島西海岸，容易銜接 17:45 預約'] },
    ],
    extraTimeOptions: [
      { title: '淡路夢舞台圓形廣場與海回廊', reasons: ['安藤忠雄建築特色集中', '免費且與原行程同場域'] },
    ],
  },
  '2026-08-29': {
    weather: '上午可能有雷雨，之後多雲且非常潮濕',
    temperature: '26–32°C',
    rain: '降雨機率 30%｜雨量約 7.3 mm',
    heatRisk: '中暑風險高：洲本城、鳴門公園與眉山皆有爬升',
    wind: '鳴門最大風速約 11 km/h｜浪高最高約 0.48 m',
    activity: '全程最高',
    steps: '約 8,000–11,000 步',
    stairs: '約 200–350 階',
    slope: '洲本城與眉山坡度明顯',
    driving: '約 5 小時',
    fixedTimes: '11:30 Ocean Terrace｜20:00 阿波舞公演',
    tide: '鳴門海峽 12:40 南流最快、19:00 北流最快；15:30 渦之道已離午間最佳時段一段時間，以橋景與海上步道為主。',
    rainOptions: [
      { title: '取消洲本城與慶野松原，保留 S BRICK、EDDY 與阿波舞', reasons: ['把戶外爬坡改成室內展館', '仍保留淡路、鳴門、德島三段代表體驗'] },
      { title: '眉山纜車改為阿波舞會館提早入場', reasons: ['雷雨或強風時不需上山', '可在室內休息並看阿波舞資料'] },
    ],
    extraTimeOptions: [
      { title: '大鳴門橋架橋記念館 EDDY', reasons: ['與渦之道步行相連', '能用互動展覽理解漩渦與大橋結構'] },
      { title: '洲本市民廣場紅磚建築群', reasons: ['緊鄰 S BRICK', '平地短走、適合拍照'] },
    ],
  },
  '2026-08-30': {
    weather: '炎熱、非常潮濕，午後有短暫陣雨',
    temperature: '26–33°C',
    rain: '降雨機率 35%｜雨量約 2.4 mm',
    heatRisk: '中暑風險很高：港區與服務區廣場曝曬強',
    wind: '鳴門最大風速約 11 km/h｜浪高最高約 0.48 m',
    activity: '中等',
    steps: '約 5,000–7,000 步',
    stairs: '約 80–150 階',
    slope: '鳴門橋紀念館周邊有坡道，船上需站穩',
    driving: '約 4 小時 10 分',
    fixedTimes: '12:50 觀潮船',
    tide: '鳴門海峽 13:20 南流最快；12:50 船班正好涵蓋接近最佳潮流的時段。航程約 60 分鐘。',
    rainOptions: [
      { title: '保留觀潮船，取消絵島與戶外觀景', reasons: ['船班是當日固定核心體驗', 'Nojima Scuola 與淡路 SA 都有室內空間'] },
      { title: '若船班停航，改走渦之道與 EDDY 共通票', reasons: ['仍可在大鳴門橋上看潮流', '互動展館不受降雨影響'] },
    ],
    extraTimeOptions: [
      { title: '福良港足湯「うずのゆ」', reasons: ['就在乘船區旁', '免費且適合船班前後短休息'] },
      { title: '淡路 SA 大觀覽車', reasons: ['一圈約 15 分鐘，容易控制停留時間', '可看明石海峽大橋與神戶方向夜景'] },
    ],
  },
  '2026-08-31': {
    weather: '炎熱潮濕，午後可能有短暫雨',
    temperature: '25–32°C',
    rain: '降雨機率 33%｜雨量約 2.7 mm',
    heatRisk: '中暑風險中等：主要活動在飯店與航廈內',
    wind: '最大風速約 17 km/h',
    activity: '低',
    steps: '約 3,000–5,000 步',
    stairs: '少量，航廈可使用電梯',
    slope: '幾乎沒有',
    driving: '約 1 小時 10 分',
    fixedTimes: '12:45 JX1835 起飛',
    rainOptions: [
      { title: '維持原行程，直接進入神戶機場第二航廈', reasons: ['全程以室內動線為主', '不增加返程日風險'] },
    ],
    extraTimeOptions: [
      { title: '神戶機場觀景台', reasons: ['位於同一航廈區域', '可看跑道、神戶港與飛機起降'] },
    ],
  },
}

export const AWAJI_PLACE_GUIDES: Record<string, PlaceGuide> = {
  'ramen-ichiraku-nijigen': { duration: '45 分鐘', cost: '每人約 ¥1,000–1,800', queue: '午餐時段中等', parking: '使用二次元之森停車場', highlights: ['一樂拉麵', '拉麵搭配火影忍者主題餐點', '限定飲品與紀念杯'], sourceUrl: 'https://nijigennomori.com/price/', hours: '平日 11:00–15:00、16:00–18:00' },
  'nijigen-no-mori-shinobi': { duration: '2 小時', cost: '成人票依日期約 ¥3,300–3,900', queue: '暑假午後偏高', parking: '大型園區停車場；步行距離較長', highlights: ['天之卷立體迷宮', '地之卷任務解謎', '火影岩與忍里場景拍照'], sourceUrl: 'https://www.nijigennomori.com/naruto_shinobizato/', hours: '平日通常 10:00 開始，暑假依官方票券時段' },
  'awaji-sunset-line': { duration: '30–60 分鐘', cost: '免費', queue: '低', parking: '只停合法停車區，不在路肩臨停', highlights: ['瀨戶內海夕景', '西海岸海景', '短距離平坦散步'], sourceUrl: 'https://www.awajishima-kanko.jp/' },
  'map-import-garb-costa-orange': { duration: '60–90 分鐘', cost: '單點約 ¥1,500–4,800；夕陽套餐 ¥7,700', queue: '晚餐時段高，已訂位', parking: '園區約 300 台免費車位', highlights: ['薪窯瑪格麗特披薩', '淡路島吻仔魚與海苔義大利麵', '淡路島鮮魚或黑毛和牛料理'], sourceUrl: 'https://garbcostaorange.jp/menu/', hours: '晚餐 17:00–21:00，餐點最後點餐 20:00' },
  'aeon-awaji': { duration: '30–40 分鐘', cost: '依採買內容', queue: '晚間低至中等', parking: '商場停車場', highlights: ['補充飲水與早餐', '淡路島零食與伴手禮', '日用品一次購足'], sourceUrl: 'https://www.aeon.com/store/' },
  'map-import-boulangerie-rural': { duration: '30 分鐘', cost: '每人約 ¥600–1,200', queue: '開店後熱門麵包可能較快售完', parking: '店前少量車位', highlights: ['現烤可頌類麵包', '鹹味惣菜麵包', '咖啡或當日季節麵包'], sourceUrl: 'https://www.instagram.com/boulangerie.rural/', hours: '週三至週日 08:00–18:00；8/28 週五正常營業' },
  'map-import-yumebutai': { duration: '60 分鐘', cost: '百段苑與公共建築區免費', queue: '低', parking: '地下停車場 600 台，¥700／次', highlights: ['百段苑', '圓形廣場與水庭', '海回廊與大阪灣景觀'], sourceUrl: 'https://www.yumebutai.co.jp/yumebutai_guide/', hours: '百段苑與展望區 07:00–22:00，電梯至 18:00' },
  'sea-church-awaji': { duration: '20–30 分鐘', cost: '外觀與公共區域免費', queue: '低', parking: '與淡路夢舞台共用地下停車場', highlights: ['十字形採光', '安藤忠雄清水模空間', '教堂與海景軸線'], sourceUrl: 'https://www.yumebutai.co.jp/' },
  'honpukuji-mizumido': { duration: '40–50 分鐘', cost: '成人 ¥400、兒童 ¥200', queue: '低', parking: '免費，普通車約 30 台', highlights: ['蓮池中央階梯', '地下朱紅色本堂', '安藤忠雄清水模建築'], sourceUrl: 'https://www.awajishima-kanko.jp/manual/detail.html?bid=454', hours: '09:00–17:00，全年無休' },
  'map-import-taidrobou': { duration: '60–75 分鐘', cost: '二種鯛料理比較御膳 ¥4,900 起', queue: '已訂位；週五午餐仍可能等候出餐', parking: '店家大型停車場', highlights: ['二種鯛料理比較御膳', '鯛刺身與炙燒', '海景座位'], sourceUrl: 'https://www.shichicafe.com/taidoroboo/', hours: '平日 11:00 起營業' },
  'map-import-awaji-hanasajiki': { duration: '60–90 分鐘', cost: '入園免費；普通車停車 ¥200', queue: '暑假午後中等', parking: '普通車約 200 台', highlights: ['高原花田全景', '明石海峽與大阪灣景觀', '天空迴廊觀景台'], sourceUrl: 'https://awajihanasajiki.jp/5974/', hours: '8/28 09:00–17:00，最後入園 16:30' },
  'naruto-ferry-fixed-activity': { duration: '30–60 分鐘', cost: '招牌舒芙蕾鬆餅約 ¥1,000 起', queue: '熱門時段高，已訂位', parking: '約 200 台', highlights: ['幸福鬆餅原味', '季節水果鬆餅', '海景露台與岬角拍照區'], sourceUrl: 'https://magia.tokyo/shop', hours: '平日 10:00–20:00，最後點餐 18:45' },
  'cosmos-shizuki': { duration: '20–30 分鐘', cost: '依採買內容', queue: '晚間低', parking: '店前停車場', highlights: ['飲水與電解質飲料', '防曬與常用藥品', '隔日早餐與車上點心'], sourceUrl: 'https://www.cosmospc.co.jp/shop/' },
  'familymart-shizuku-otoshi': { duration: '20–30 分鐘', cost: '每人約 ¥500–900', queue: '低', parking: '店前停車位', highlights: ['飯糰或三明治', 'FAMIMA CAFÉ 咖啡', '優格、水果與電解質飲料'], sourceUrl: 'https://store.family.co.jp/points/52703', hours: '24 小時營業' },
  'sumoto-castle': { duration: '45–60 分鐘', cost: '免費', queue: '停車位少，週末早上中等', parking: '上城兩處約 10／20 台，免費；入口狹窄', highlights: ['模擬天守與洲本灣全景', '珍貴的登石垣遺構', '本丸大石階'], sourceUrl: 'https://www.city.sumoto.lg.jp/site/tunagarumachi/16885.html' },
  'retro-komichi': { duration: '30–40 分鐘', cost: '免費', queue: '低', parking: '使用洲本市區公共停車場', highlights: ['昭和街屋與巷弄', '洲本老城街景', '在地小店外觀與攝影'], sourceUrl: 'https://www.awajishima-kanko.jp/' },
  'map-import-sbrick-warehouse': { duration: '35–50 分鐘', cost: '公共空間免費；餐飲另計', queue: '週末中等', parking: '專用 8 台，滿位使用洲本巴士中心前停車場', highlights: ['紅磚倉庫建築', 'FOOD BASE 起司與披薩', '市民廣場與室內休息區'], sourceUrl: 'https://sumoto-brick.jp/about/', hours: 'S BRICK 10:00–18:00' },
  'map-import-ocean-terrace': { duration: '90 分鐘', cost: '主餐約 ¥3,500–8,500；兒童餐 ¥2,000', queue: '已安排 11:30，週六建議預約', parking: '免費 50 台', highlights: ['淡路牛自助烤肉', '淡路雞或惠比壽麻糬豬組合', '約 30 種沙拉、配菜與甜點'], sourceUrl: 'https://ocean-terrace.capoo.jp/', hours: '午餐 11:30–15:30，最後入店 14:00' },
  'map-import-keino-beach': { duration: '20–30 分鐘', cost: '免費', queue: '低', parking: '海灘周邊停車區', highlights: ['日本夕陽百選海岸', '黑松林景觀', '五色卵石海灘'], sourceUrl: 'https://www.awajishima-kanko.jp/' },
  'uzu-no-michi': { duration: '45–60 分鐘', cost: '成人 ¥510；與 EDDY 共通票成人 ¥900', queue: '暑假週末中高', parking: '鳴門公園停車場 200 台，普通車 ¥500', highlights: ['海上 45 公尺玻璃地板', '大鳴門橋橋下步道', '鳴門海峽潮流與橋景'], sourceUrl: 'https://www.uzunomichi.jp/usage-guide-uzu-no-michi/', hours: '暑假 08:00–19:00，最後入場 18:30' },
  'bizan-ropeway': { duration: '60–75 分鐘', cost: '成人來回 ¥1,500', queue: '夕陽前後中高', parking: '使用阿波舞會館周邊停車場', highlights: ['眉山山頂德島市景', '吉野川與紀伊水道遠景', '往返纜車空中景觀'], sourceUrl: 'https://www.awaodori-kaikan.jp/', hours: '4–10 月 09:00–21:00' },
  'awaodori-kaikan': { duration: '50 分鐘', cost: '夜間公演成人 ¥1,600', queue: '20:00 夜間公演建議提早入場', parking: '會館停車位有限，使用周邊停車場', highlights: ['專業連演出', '觀眾一起學阿波舞', '樂器與舞步近距離觀賞'], sourceUrl: 'https://www.awaodori-kaikan.jp/', hours: '夜間公演 20:00–20:50' },
  'menoh-tokushima': { duration: '45–60 分鐘', cost: '每人約 ¥900–1,400', queue: '公演散場後中高', parking: '使用市區停車場', highlights: ['德島拉麵肉玉入', '生雞蛋搭配濃厚豚骨醬油湯', '餃子或炒飯'], sourceUrl: 'https://www.menya-oh.com/' },
  'map-import-naruto-bridge-memorial': { duration: '50–65 分鐘', cost: '成人 ¥620；與渦之道共通票成人 ¥900', queue: '開館初段低', parking: '鳴門公園停車場普通車 ¥500', highlights: ['漩渦形成互動展示', '大鳴門橋施工與結構展示', 'Play the Eddy 體驗區'], sourceUrl: 'https://www.uzunomichi.jp/eddy/usage-guide-eddy/', hours: '暑假 09:00–18:00，最後入館 17:30' },
  'map-import-uzuno-oka': { duration: '60–90 分鐘', cost: '每人約 ¥1,000–2,500', queue: '週日午餐高', parking: '園區免費停車場', highlights: ['淡路島洋蔥牛肉堡', '海膽涮涮鍋或海鮮料理', '巨大洋蔥裝置與大鳴門橋展望'], sourceUrl: 'https://rest.uzunokuni.com/' },
  'uzushio-cruise-fukura': { duration: '航程 60 分鐘；另留 40–50 分鐘報到', cost: '成人 ¥3,000；未就學幼兒每位成人可帶 1 位免費', queue: '週日高，售票與登船前最繁忙', parking: '道之驛福良周邊停車場免費', highlights: ['近距離觀察鳴門漩渦', '從船上穿越大鳴門橋下方', '咸臨丸或日本丸甲板海景'], sourceUrl: 'https://www.uzu-shio.com/timetable', hours: '12:50 已排定；建議 40–50 分鐘前到達' },
  'nojima-scuola': { duration: '45–60 分鐘', cost: '參觀免費；餐飲約 ¥400–1,700', queue: '週日下午中等', parking: '免費約 80–95 台', highlights: ['舊小學校舍再生建築', '淡路牛筋咖哩或淡路洋蔥披薩', '自家製起司蛋糕與島檸檬蘇打'], sourceUrl: 'https://nojima-scuola.com/faq/', hours: '週日市集 10:00–19:00、咖啡 10:30–18:00' },
  'eshima': { duration: '20–25 分鐘', cost: '免費', queue: '低', parking: '岩屋港周邊有料停車場；絵島本體禁止進入', highlights: ['國生神話地景', '砂岩層理與侵蝕外觀', '岩屋港與明石海峽背景'], sourceUrl: 'https://www.city.awaji.lg.jp/' },
  'awaji-sa-ferris-wheel': { duration: '15–30 分鐘', cost: '一般票 ¥800', queue: '週日夕陽時段中高', parking: '淡路 SA 大型停車場', highlights: ['一圈約 15 分鐘', '明石海峽大橋全景', '神戶與大阪灣方向夜景'], sourceUrl: 'https://www.jb-highway.co.jp/sapa/awaji_down.html', hours: '09:00–21:00，最後搭乘 20:45' },
  'awaji-sa-highway-oasis': { duration: '45–60 分鐘', cost: '每人約 ¥800–1,800', queue: '週日晚餐中高', parking: '小型車 348 台', highlights: ['淡路島洋蔥拉麵或咖哩', '淡路島漢堡', '明石燒、甜點與伴手禮'], sourceUrl: 'https://www.jb-highway.co.jp/sapa/awaji_down.html', hours: '美食區 24 小時，餐廳 07:00–21:00' },
}
