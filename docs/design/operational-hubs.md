# Operational Hubs 前端規格（Issue 69）

## 1. 目標

建立四個可重複套用的 Hub：

1. Reservations Hub（預約與票券）
2. Lodgings Hub（住宿）
3. Dining & Supply Hub（餐飲與補給）
4. Tide & Conditions Hub（潮汐與動態條件）

共用原則：

1. 先解決「現在要知道什麼」而不是「還原營運邏輯推理」
2. 同一套 status / source / freshness / conflict 表意語彙
3. 所有卡片都能回到 itinerary（deep link）
4. 未確認資料要明確標示，不隱藏、不誤標為已確認
5. 不涉外部資料抓取與欄位推算，僅渲染 read model / public bundle

## 2. Shared Hub Framework（統一結構）

每個 Hub page 都應使用以下區塊：

1. Hub Header
2. Summary Stats
3. Offline / stale banner
4. Critical Alerts
5. Primary + Secondary Actions
6. Item Cards with status badge
7. Source drill-down row
8. Footer：last checked / next recheck / print summary / back link

### 2.1 狀態語彙

頁面顯示以下 status state（只做視覺，不做 domain 判斷）：

- `confirmed`
- `estimated`
- `unverified`
- `stale`
- `conflict`
- `unresolved`
- `unknown`

### 2.2 Hub Card 結構（最小欄位）

建議欄位順序：

1. 左側：status chip
2. 標題 / 補充標籤（day / kind / source）
3. 核心資訊（日期、時間、地點、關鍵限制）
4. 行動（copy、map、phone、links、ics）
5. 補充（confidence、freshness、last checked）
6. Conflict / stale 說明

### 2.3 Deep-link 契約

從 Hub card 的任何 actions 與摘要連結回到 itinerary 時必須至少提供：

1. day slug（`YYYY-MM-DD`）
2. item id（bundle item id）
3. source page route fragment（`#item-id`）

### 2.4 Offline / 快取

- 只要 cache 可讀：顯示資料版本（`bundle.meta.generated_at` 或對應資料來源版本）
- 外部 action（電話/地圖/官網）顯示網路依賴提示
- 無資料時使用「offline-empty」樣式，不顯示誤導性成功標語

### 2.5 Print Summary 規範

每個 Hub 都有可列印摘要（最少）：

1. 當前 hub title
2. 重要 item 列表（以日期排序）
3. status + source + freshness
4. 注意提醒（若有）

## 3. Reservations Hub

### 3.1 要呈現的群組

1. outbound flights
2. return flights
3. fixed reservations
4. rental cars
5. attractions / boat / tickets

### 3.2 卡片欄位

- confirmed / pending / cancelled / unresolved
- check-in / report-by / departure / cancellation deadline
- party size / pax
- source / confidence / freshness
- last checked / next recheck

### 3.3 actions

- copy summary（公共資訊版本）
- copy Japanese confirmation（公共資訊版本）
- add to calendar（單筆/一組）
- official link / maps / phone
- deep link 到 day item

### 3.4 隱私規則

- 不展示完整 booking code
- 不展示旅客姓名、Email、私人電話、護照、付款資料
- 未提供時不猜測資料
- 預約若 `unresolved` 必保留；不得因缺欄位隱藏

## 4. Lodging Hub

### 4.1 呈現順序

- 以 `check_in` / `day` + `nights` 排序，非既有候選順序

### 4.2 卡片欄位

- name / japanese_name
- stay dates / nights / check-in / check-out
- address / maps / phone
- status（selected / booked / verified）
- parking / fee / height_limit / large_vehicle
- entrance, luggage_unloading
- elevator / floor / luggage_handling
- laundry / kitchen / microwave
- nearby supermarket / convenience / breakfast / dinner / medical
- unknown facility 明示為 unknown，不轉為 false
- source + freshness + conflict

### 4.3 UX 附件要求

- 換日提醒（checkout/luggage/route）
- 一鍵複製地址
- 一鍵導航
- 一鍵撥號
- 查看次日行程（deep link）

## 5. Dining & Supply Hub

### 5.1 結構

- 按 day + meal slot 分組
- 每組顯示：
  1) first choice
  2) backup
  3) low-queue
  4) supermarket deli / convenience fallback
  5) hotel-nearby fallback

### 5.2 餐廳卡欄位

- cuisine / recommended dishes
- seven-person seating
- reservation status / url
- opening interval / closed day / last order
- price signal / parking
- queue risk
- source / freshness / operational conflict
- child / elder notes（僅有 evidence 時）
- smoking policy（僅有 evidence 時）

### 5.3 過濾與排序

- 不只顯示網紅店
- `closed` / `stale` / `unknown` 不可顯示為 success 樣式
- searchable by name / meal / tags
- 快速切換官方 tags：最穩定、最有特色、排隊最少（僅使用 read model 提供值）

## 6. Tide & Conditions Hub

### 6.1 視覺化

- date cards
- time-axis bands（high/low tide）
- condition badges（strong current / closure / weather warning）
- recommended options：boat / land / suspension

### 6.2 內容欄位

- 每日 high/low 時刻與潮高
- strong-current windows
- recommended day + evidence-backed reason
- no-guarantee warning
- operating / report-by times
- child rule / elder accessibility / seasickness
- parking and contingencies
- source / retrieved_at / freshness / next recheck

### 6.3 合規限制

- 不進行潮汐推算
- 不承諾 guaranteed outcome（例如「一定可見渦流」）
- forecast 與 observed 要明示不同來源與可靠度

## 7. Cross Hub 互動規則

1. 任一 Hub 卡可回到 itinerary item
2. itinerary item 可開啟對應 Hub detail
3. source badge 點擊展開 source detail（不離開主流程）
4. 所有 copy/phone/maps actions 共用 style token
5. 全域搜尋可命中 public-safe 的 hub content
6. mobile 返回時保留原定位（回到原 scroll/item）

## 8. 測試規劃（由前端承接）

1. confirmed / unresolved / stale / conflict / empty 狀態快照
2. 隱私 redaction 測試：no booking secret, no private phone/passport
3. `copy` + `maps` + `phone` + `ics` 行為測試
4. 深鏈回到 itinerary 測試
5. source/freshness 轉譯測試
6. offline 模式快取核心資料測試
7. 390 / 430 / 768 / 1440 快照
8. print snapshot

## 9. 依賴與非目標

依賴：

1. #59（可信 evidence）
2. #60（itinerary / transport / tide source）
3. #61（public bundle fields）

非目標：

- 不做 provider raw payload 解讀
- 不進行潮汐計算與餐廳 eligibility 判斷
- 不做研究、訂位 API 呼叫

