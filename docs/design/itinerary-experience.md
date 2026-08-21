# Itinerary Experience (Issue #67)

## 目標
把現有淡路島行程頁從純清單改為可在行程現場使用的高密度時間軸工作區：
- Day 導覽、每日指標、timeline 分類視覺化
- Plan A/B/C + Decision Gate 與 fixed anchor 保留
- 全行程搜尋與快速 now/next 流程
- unknown 狀態明確化，不虛構資料

## 當前基準
Issue #67 讀取基礎為 `web/src/App.tsx` 現況：
- 目前是固定 5+日的 `day-tabs` 及每日日程 `<ul>` 清單
- 只呈現 `kind/start_at/end_at/place_id/notes`
- 無 travel leg、無備選方案、無搜尋索引、無可用時間軸層級
- 已有離線提示與地圖/複製 action，可沿用為最小 fallback

## Scope 對應表（v1.0）

### 1. Day navigation
- sticky tabs（可水平捲動）
- day 主題/日期（含今天/完成/未來狀態）
- keyboard arrow + hash deep link（`#day=YYYY-MM-DD`）
- tabs 高度需避免遮罩主要內容（safe-area）

### 2. Daily header
- day theme / lodging anchor / energy / walking / outdoor / drive total / attraction count / optional count / alerts / freshness
- 不只靠色彩：icon + label 形式

### 3. Timeline 語意化
- 分類：flight / rental car / drive / transit / walk / attraction / meal / hotel / reservation / rest
- 每個 item 顯示：時間、名稱/日文名、fixed/optional/cancelable、預估停留、transfer/parking/walking/buffer、reason/plan、notes、validation、source refs、quick actions
- unresolved 顯示明確 `待補` 標籤

### 4. Travel leg cards
- 只用 bundle 已有資料顯示 route metadata
- 不存在時顯示 `未提供/unknown`
- 永不以 0 取代未提供資料

### 5. Plan A/B/C
- 僅顯示 validator-approved alternatives（無方案顯示 `unavailable`）
- 固定 anchor 在各方案共用可見
- 顯示 trigger / trade-off / 時間影響 / 取消項目

### 6. Decision Gates
- gate 與 item 關聯並可定位到該項目
- 含：未離站超時、停車排隊、延誤、幼童午睡

### 7. Search + filters
- 查詢：名稱（中日）、景點/餐廳/住宿/預約、地址、備註、category
- day / status / optional / fixed filter
- 點選結果可定位到 day + item
- 僅使用 public bundle public-safe 欄位建 index

### 8. On-trip quick mode
- 今日行程 / now & next item（僅在時間可安全判斷）
- fixed anchor countdown
- 一鍵地圖 / 一鍵撥號 / 複製地址
- 跨時區或缺時資料回退到 `unknown`，不畫預測值

## 變更原則（共通）
1. 不重排 itinerary、不重算路線、不生成備案（只轉譯 read model）
2. `fixed` 需有明顯但不突兀權重；`optional / cancelable` 需可辨識
3. 所有 unknown 數值/時間顯示 `待補` 或 `unknown`
4. reduced motion 時段落一致（禁用動畫）
5. 保留現有離線快照可讀性（至少包含核心 timeline）

## 建議拆解順序（先小後大）
1. 建立資料 adapter：`Bundle -> render model`，集中整理欄位命名與 unknown 狀態
2. 重構 Day header + timeline 的基本版型
3. 加入 fixed / optional / cancelable 的標記與 legend
4. 加入 Plan 切換與 Plan 列表欄位驗證顯示
5. 加入 decision gates 與 item 關聯標記
6. 全域搜尋 + filters + jump to anchor
7. 快速模式 panel + now/next safety 邏輯
8. layout audit（390×844, 430×932, 768×1024, 1440×900）與列印樣式

## 對應資料需求（bundle）
- itinerary: `days[*].items`。
- daily metrics: `days[*].summary`（至少先 fallback）、`selected`, `validation`。
- route details: read model 的 leg / route block。
- 替代方案: alternatives / conditions 來源。
- status/alerts/freshness: validation/message/generated_at。

## 風險與隔離
- 目前 `issue-61` 已佔用 `web/src` 寫權，issue #67 實作需與其共享邊界協調後，才能進行實際 UI 程式變更。
- 先以本文件完成設計對齊，待 `web/src` 寫入許可後進行頁面實作與測試。

## 現況 review（Issue #61 工作版）

### 已有可沿用的基礎
1. `web/src/lib/google-maps-links.ts` 已有 route segment 拆解與 maps 行為抽象，適合被 Issue #67 直接復用。
2. `web/src/App.tsx` 已逐步把地點欄位擴充到停車、地址、電話、導航點、距離/時間字串格式化，對於日後 timeline 視覺化有正向基礎。
3. 已有 `source_state`、`freshness` 等可被拿來表示 `unknown/state`。

### 缺口（仍未覆蓋 Issue #67 AC）
1. 缺少 Day sticky + state（today / completed / future）與 keyboard/arrows。
2. 缺少每日彙整指標：energy、walking、outdoor、drive total、optional count。
3. 缺少 Plan A/B/C 面板與 Decision Gate。
4. 缺少全行程搜尋與條件過濾器。
5. 缺少 now/next 快速模式與 fixed anchor 倒數。
6. 未有 `print` 樣式與無障礙焦點巡覽驗證。
7. Timeline item 仍以條目為主軸，還未達到 item category 直覺差異化。

### 目前程式審視到的高優先修正
1. 預設 active day 算式在部分分支仍有可能回傳不可達值，建議統一以 `Math.max(0, min(index, total-1))`，避免空陣列邊界。
2. 解析時間/路段時建議保留 `unknown` 狀態，不要用 0 代替；目前部分 formatter 已有這件事，但需要全局一致。
3. 搜尋索引必須只取 public-safe 欄位，不能讀取保密欄位或非必要 provenance。

## 這個 Issue 的最小可交付清單（v1.0）
1. `itinerary` timeline 首版：至少做到日數/固定/可選/未知狀態可辨識。
2. `search`：名稱中文日文與地點名 + day filter + jump 到對應 day/item。
3. `quick-mode`：今日/now/next 的 safe 判斷分支（unknown fallback）。
4. `plan tabs`：三方案可切、無方案顯示 unavailable。

## 驗收對照（可直接貼到 PR 檢核）
1. Core itinerary UX 1–2 項通過即可進行下一版擴充。
2. 每完成一個 AC 群組，對應新增/更新測試。
3. 避免任一 render 中對未知值回退為 0。

## Review handoff 結果（給 issue61 實作者）

### 立即可驗證項目
1. `web/src/App.tsx` 目前已整併 theme + maps link + 基本 status，建議本 issue 67 的剩餘實作採「增量改造」方式繼續，不要重構整頁。
2. 目前 `unresolvedReservations` 的 `useMemo` 可能有重複 dependency 的型別污染風險（目前檔案上已現身 2 次），建議在 refactor 時順手清理。
3. `setActiveDay(Math.min(0, Math.max(data.days.length - 1, 0)))` 為邊界 bug（永遠回傳 0）；建議使用 `setActiveDay(Math.max(0, Math.min(initialIndex, data.days.length - 1)))`，並在 `bundle` 無資料時保持 0。

### 優先修正（對應 AC）
1. Day 導覽
1.1. `role=tablist` 保留不變，新增 `tablist` 水平可捲、selected/today/completed/future 狀態 class。
1.2. 深連結改用 `hash=day-<index>` 或 `#day=<date>` 均可，需回到對應 section.
2. Timeline 分類視覺
2.1. 在 `BundleDayItem.kind` 以外再加入 status metadata（fixed/optional/cancelable/unresolved）轉譯。
2.2. 未知 start/end 時顯示 `待補`，不得顯示 0 分鐘。
3. Plan A/B/C / Decision Gate
3.1. 不改動已排程事實，僅切頁/顯示 validator 允許項目。
3.2. 無可行替代時顯示明確 `unavailable` 區塊，不顯示空白建議。
4. 搜尋與 filters
4.1. 建立 public-safe 倒排欄位 index：中日名稱、類型、地址、day、notes、status。
4.2. 點擊結果跳到當日與該項目（加上可重取焦點的 anchor）。
5. now / next quick mode
5.1. 僅在時間可比較時計算，否則顯示 `unknown`。
5.2. fixed anchor 倒數需標明「時間未齊全」與 fallback。

### 里程碑建議（可直接提交 commit 的順序）
1. 新增 `day-tabs + header metrics + timeline token`（含 state 標籤）
2. 新增 `search index + search panel + filter panel`
3. 新增 `plan tabs` 與 `unavailable` 狀態
4. 新增 `decision gates` 與 item anchor 關聯
5. 新增 `now/next quick mode`
6. 進行 a11y/print / breakpoints 最後收斂

## 直接交接給 reviewer 的待修項目（issue 67） 

### 1. High 影響（必先修）
1. Day tab 深連結與鍵盤操作
1.1. 確認 `#day=<date>` 或 `#day=<index>` 可重現定位
1.2. keyboard 左右鍵在 focus state 下可切換日

2. 行程資訊辨識度
2.1. 每日時間軸需有固定/可選/可取消/未完成四種狀態標籤
2.2. unknown 時間不得顯示 00:00 或 0 分鐘；需顯示 `待補`

3. Plan A/B/C
3.1. `Plan` panel 內 `unavailable` 要顯示明確 CTA 或「無可行替代」
3.2. fixed anchor（flight/hotel）在所有方案保留

### 2. Medium 影響（建議修）
4. Search index
4.1. index key 限定 public-safe 欄位
4.2. 搜尋結果點擊時帶出對應 day 與 item id

5. Decision Gates
5.1. gate 卡要有 `trigger`、`tradeoff`、`linked item`（可跳）

6. Quick mode
6.1. now/next 顯示邏輯需有可判斷條件保護（例如 timezone/時間缺失）

### 3. 低風險收斂
7. Layout 與 print
7.1. 手機 390×844 / 430×932 長文換行與按鈕最小 44px
7.2. print mode 僅輸出核心時間軸、fixed anchors、routes、decision gates

## PR 交接稿（可直接貼到 issue comment）
1. 目前 PR 77 現況
1.1. 已完成：Issue 67 需求拆解、現況 review、缺口與實作順序
1.2. 未完成：`web/src` UI 程式實作（權限仍在 issue61）

2. 要求的下一步簽核
2.1. 請在 issue61 完成 `web/src` 寫權後，先合併本 PR 的設計指引為正式交付規格
2.2. 再由 issue61 實作者依本文件逐條實作並補 PR 驗證
