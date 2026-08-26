# 前端執行架構

## 範圍

`web/` 只有一個瀏覽器組合入口。`src/main.tsx` 啟動 `TripApp`，由
`TripApp` 管理路由、主行程資料載入狀態、外框與頁面。專案刻意不保留
`src/App.tsx`，避免相容入口或功能開關建立第二套正式應用程式。

## 執行層次

1. `main.tsx`：啟動瀏覽器應用程式與載入樣式。
2. `app/TripApp.tsx`：選擇路由、管理主行程資料狀態並組合頁面。
3. `layouts/`：響應式外框與導覽。
4. `pages/`：呈現只讀的旅遊資訊；不得自行研究、排序、推算或修改主行程內容。
5. `contracts/` 與 `hooks/`：驗證公開資料、解析網址與管理導覽。

## 公開資料與登錄檔

登錄檔是部署設定。載入器讀取登錄檔並取得唯一一份
`<canonical_url>/public-bundle.json`，不嘗試舊路徑或猜測備援路徑。
`parseBundle` 會在頁面收到資料前驗證必要欄位；格式錯誤或無法取得時，
由外框呈現明確的錯誤狀態。

## 使用者資料

目前網站不要求旅客勾選清單、填寫備忘或記錄支出，也不把任何資料寫入
瀏覽器儲存空間。所有畫面只讀取公開主行程，旅途中重新開啟網站即可看到
相同內容。

## 路由與部署

雜湊路由由 `app/route-registry.ts` 解析與產生，深層連結和瀏覽器上一頁共用
相同規則。Vite 從最小化的 `index.html` 與 `/src/main.tsx` 建置，因此原始碼
與部署版本走相同入口。網站不註冊離線快取；旅遊資訊以每次開啟時載入的
已部署版本為準。

## 現行功能歸屬

| 功能 | 現行模組 | 狀態 |
| --- | --- | --- |
| 主行程資料載入與驗證 | `useBundleLoader` + `parseBundle` | 使用中 |
| 載入與錯誤狀態 | `TripShell` + `TripApp` | 使用中 |
| 頁面與每日導覽 | `route-registry` + `useTripNavigation` | 使用中 |
| 總覽與每日行程 | `OverviewPage` + `ItineraryPage` | 使用中 |
| 地圖 | 景點與餐廳名稱直接連到 Google Maps | 使用中 |
| 預約與固定時間 | `ReservationsPage` | 使用中 |
| 行前攜帶物品 | `PackingPage` | 使用中 |
| 每日餐飲 | `FoodPage` | 使用中 |
| 日語速查 | `JapanesePage` | 使用中 |
| 響應式外框與主題 | design-system/theme modules + `TripShell` | 使用中 |

## 品質檢查

可重現的本機檢查指令如下：

```sh
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
npm --prefix web run test:e2e
```

單元測試涵蓋公開資料拒絕、路由往返、網址解析與架構回歸。端對端測試會
啟動正式預覽版本，並以手機與桌面尺寸檢查總覽、每日行程、餐飲、預約與
行前攜帶物品頁面。
