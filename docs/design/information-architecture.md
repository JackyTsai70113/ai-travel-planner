# Issue 65 App Shell 資訊架構

本文定義 Issue 65 在 Golden Trip Web 的頁面架構、路由與導覽行為。

1. 組成層
   1. web/src/app/AppProviders.tsx: 應用 bootstrap 容器（目前為 composition root placeholder）
   2. web/src/app/TripApp.tsx: 讀取 bundle、解析 route、決策 shell 狀態與主要 section 渲染
   3. web/src/layouts/*: Shell、sidebar、header、mobile navigation、drawer
   4. web/src/pages/*: 各 section 對應 page
   5. web/src/hooks/*: bundle 載入與 route state 管理
   6. web/src/contracts/trip.ts: bundle 型別、工具函式與顯示文案映射
   7. web/src/app/route-registry.ts: section registry 與 hash route contract

2. Section 與 deep link
   1. 旅行總覽 `overview`
   2. 每日行程 `today`
   3. 地圖與自駕 `map`
   4. 預約與票券 `reservation`
   5. 潮汐／動態條件 `tides`
   6. 餐飲與補給 `food`
   7. 住宿 `lodging`
   8. 旅行手冊與緊急資訊 `handbook`
   9. 行李與備忘 `packing`
   10. 行李與預算 `budget`
   11. 實用日文 `japanese`
   12. 資料來源與更新狀態 `sources`

3. URL 形式
   1. Section only：`#/section`
   2. Day based section：`#/section/YYYY-MM-DD` 或 `#/section/3`（支援 1-based 索引）
   3. Item deep-link：`#/today/YYYY-MM-DD/item-id` 或 `#/today/3/item-id`

4. 導覽行為
   1. 桌機：左側 sidebar 固定區塊
   2. 行動：頂列 `mobile-topbar`、底部快速 nav；需要完整 section 一覽時可開啟 drawer
   3. 失效 day route：僅在當前 section 需要 day 且日子無法對應時顯示 route-not-found，導向可用 section 頁面
   4. 回到上次 day：在 section 切換與行程切換時，將有效 day 寫入 localStorage（`golden_trip_last_day_${section}`）

5. 狀態顯示
   1. loading
   2. invalid
   3. critical
   4. offline-cache
   5. offline-no-cache
   6. route-not-found
   7. newer-version（由 useBundleLoader 暫存判斷）

6. 已知限制
   1. map/food/lodging/tides 目前為骨架頁面；接續 issue 會接上 domain feature
   2. 尚未接入完整 E2E 覆蓋：Issue AC 要求的 e2e/screenshot 清單仍需在後續流程補齊
