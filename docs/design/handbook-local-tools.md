# Issue 70: Travel Handbook / Practical Japanese / Emergency & Local Planner Design

## 1. 目標

1. 把旅途中實用資訊與個人規劃工具，拆成可離線使用的前端功能區塊。
2. 公開資料與個人資料徹底分離：只讀資料放 public bundle / static pack；個人資料只放 localStorage。
3. 功能邏輯採「trip-scoped versioned」命名空間，避免跨行程污染。

## 2. 非目標

1. 不建立後端同步、帳號登入或 cloud database。
2. 不在前端儲存或上傳電話/醫療等個資。
3. 不把個人 notes / budget 自動加入 share / print / ICS / summary。
4. 不複製 issue 61 的 `kyushu_*` 或 `awaji_*` hardcode key/content。

## 3. 資料模型（最小可行）

1. `public-bundle handbooks`: `web/public/operations-read-model.json` 內新增 section
   - `id`
   - `category`
   - `title`
   - `summary`
   - `items[]`
   - `metadata`（`sourceType`、`sourceUrl`、`sourceAt`、`freshness`）
   - `tripScope`（`global` 或 day/place reference）
2. `public-bundle japanese phrases`: `web/public/japanese-phrases.json` 內新增
   - `id`, `category`, `japanese`, `kana`, `romaji`, `traditionalChinese`, `usageNote`, `placeRefs`, `sourceType`
3. `trip-scoped local storage`
   - `trip:<tripId>:checklist:v1`
   - `trip:<tripId>:budget:v1`
   - `trip:<tripId>:notes:v1`
   - `trip:<tripId>:preferences:v1`
   - 版本欄位內含 `schemaVersion`, `tripId`, `updatedAt`, payload + `sourceDataHash`（僅用於錯誤提示）

## 4. localStorage 契約

1. namespace 函式
   - `mkStorageKey({tripId, module, version}) => trip:<tripId>:<module>:v<version>`
2. 遷移
   - 支援讀取 `awaji_2026_*` 舊 key
   - 不能讀取/寫入 `kyushu_*`
   - 解析失敗時要保留原字串並輸出 user-visible recovery payload
3. 檢錯策略
   - schema 驗證失敗：保留原始值為 `*_corrupt`，引導「複製/清空/重建」流程
4. clear all
   - 提供 per-trip 清理 + 全域清理（需二次確認）

## 5. Handbook UX（Issue 70 A）

1. `category tabs` + `filters`（可多選）。
2. `全文搜尋`：日文、中文、拼音/羅馬字都能 match 指定欄位。
3. `favorite/pin`：以 local preference key 管理（不改 public data）。
4. `copy action`：每則卡片可複製關鍵句/電話/連結。
5. `deep link`：`/handbook?cat=driving&item=parking-maps`
6. `compact card` + `detail sheet`
7. `offline available`：資料已預載在 public bundle 內。

## 6. Practical Japanese（Issue 70 B）

1. 支援欄位
   - `id`, `category`, `japanese`, `kana`, `romaji`, `traditionalChinese`, `usageNote`, `placeRefs`
2. UI
   - 多欄搜尋：中文 + 日本語 + 假名 + 羅馬字
   - category filter
   - one-click 複製 `japanese`
   - Speech API
     - `speechSynthesis` + `ja-JP` 選音
     - 不支援時顯示 `speech unavailable`，並可 fallback 到「僅文字」模式
3. Contextual search
   - 餐廳、住宿、路線頁可傳入 `placeRef/category`，直接帶入預設 query

## 7. Emergency & Family Guide（Issue 70 C）

1. 核心資訊（最低）：
   - `110`, `119`, 官方旅客求助連結（含語系備援）
   - 熱點（child/elder) 應對重點
   - motion/hydration/seasickness 快速處置要點
2. `medical` 資訊只包含求援導引與注意事項，不做診斷建議。
3. 顯示 source/freshness（若來自官方變更可能來源）。

## 8. Local Planner tools（Issue 70 D）

1. Checklist
   - 預設模板由 public pack 匯入
   - add/edit/delete/check/reset
   - 進度條
2. Budget
   - record: amount/currency/category/payer/date/note
   - summary: total + category 分組
3. Notes
   - title/content/date/dayRef/placeRef
   - add/edit/delete/search
   - import/export JSON
4. Privacy 行為
   - 顯示 local-only badge
   - 只在 export/import 時暴露文字

## 9. 依賴與整合

1. 依賴 #61：public bundle schema 擴充完成後接入。
2. 依賴 #64/#65：沿用 design system 與 app shell 與 navigation。
3. 依賴 #63：離線可用由 PWA cache 保障。

## 10. 測試清單（最小）

1. storage unit tests
   - key 格式、migration、malformed、quota error path、clear-all
2. component tests
   - handbook filter/search, japanese search/filter/copy/speech fallback, budget summary
3. integration tests
   - trip 切換不污染
   - import/export roundtrip
4. offline smoke
   - handbook、phrases、emergency 在離線可讀
