# AI Travel Planner MCP 長期目標

## 方向

持續開發、測試、審查與合併本 repository，直到 AI Travel Planner MCP 能在一般 ChatGPT Chat 中穩定完成有根據的旅行規劃；之後仍持續依實際使用回饋改善，不把一次部署或單項測試當作終點。

這是本 repo 的長期產品目標。每輪工作從最新 `origin/main`、尚未完成的 GitHub Issues 與正式環境證據出發，完成相關實作、測試、review、一般 merge、部署與可執行的驗收，並把新發現記回 repo 或對應 Issue。

## 「MCP 正常可用」的驗收範圍

1. ChatGPT 一般 Chat 能發現並認證私人 AI Travel Planner MCP，能呼叫適當工具；本機 stdio 和正式 Railway Streamable HTTP 入口各自可驗證。
2. 對話能逐題補齊必要資訊，只使用使用者明確提供的內容，不猜日期、旅客、預算、住宿、路線或營業狀態。使用者能留空住宿，也可自行提供住宿資料；沒有資料就保留空白與未驗證狀態。
3. 正式 `plan_trip` 使用可追溯的 live source evidence 建立 Canonical Trip，將景點與可驗證餐點排入每日行程，正確表示未知路線、營業時間、價格與完整度；不以候選數量或頂層 `complete` 字串取代內容驗收。
4. 持久化、讀取、驗證與本機頁面 renderer 使用同一份有效 Canonical Trip。外部 provider 資料的保存、 attribution、保留期限與公開輸出須符合各來源的現行規則。
5. 公開網站是獨立的明確使用者動作；未經單獨同意不得發布。經同意後，MCP 發布工具須產生預期 GitHub Pages 網址，等待 Pages 部署，再用瀏覽器確認網頁內容。
6. 安全性與服務設定可持續維護：Railway endpoint、Bearer 認證、工具 schema、GitHub 發布憑證、資料 volume、healthcheck 和部署來源均須有最新且不含 secret 值的紀錄。

## 驗收證據分層

1. 單元／整合測試證明指定程式情境；recorded/mock provider 測試不得標成 live provider 或正式 ChatGPT 驗收。
2. CI、服務 health、MCP `tools/list`、CLI 或 MCP Inspector 證明各自的基礎設施範圍，不能取代 ChatGPT 一般 Chat 實際呼叫。
3. 涉及 MCP 部署、連線、工具或認證的變更，依 [`ChatGPT Chat MCP 上線驗收流程`](chatgpt-mcp-live-verification.md) 使用 Computer Use 在一般 ChatGPT Chat 驗收。維護者明確要求由使用者輸入 prompt 時，必須保持等待；不得改用 Work，也不得代替使用者送出 prompt。沒有這項證據時如實標記未驗收。
4. 涉及網站的外連、版型或互動時，依 repo `AGENTS.md` 的瀏覽器規格，以實際瀏覽器操作和畫面檢查驗收；靜態檢查或被攔截的 popup 不算目標網站可用證據。

## 目前正式環境基線（2026-10-08）

- Railway MCP runtime source SHA 為 `3f7df71f93c33ca06c0daf866f0c6b3d562ee71d`，deployment `f2400745-ddc7-4db3-a818-0022bacf9ed4` 狀態 `SUCCESS`；正式服務 Online，`/health` 回 HTTP 200、內文 `ok`。正式後端此前 `tools/list` 回 HTTP 200、7 個工具。
- 2026-10-08 以 Railway CLI 再次核對七項工具，並對已排定 Place ID 呼叫一次 `get_place_details`；正式工具回 HTTP 200、`available`、`Google Maps` attribution。此 Codex connector 快照只有六項工具，缺少 `get_place_details`；此差異不代表 ChatGPT Chat 的工具清單。OpenAI 自訂 MCP plugin 文件指出 app 詳細資料頁可 Refresh apps 取得更新的工具描述和 server instructions；ChatGPT Chat 實際刷新與呼叫仍待驗收，詳細程序見[上線驗收流程](chatgpt-mcp-live-verification.md)。
- PR #243 至 #256 已以一般 merge 合併。PR #250 修正網站 E2E 將行程卡數寫死為 5 的回歸；PR #252 更新 `get_trip` 與 `get_place_details` 的工具說明；PR #256 修正可排入但未被選中的景點備選項不再造成未驗證警告。
- PR #243 修正持久化／發布投影中 Google Places 候選驗證訊息殘留名稱與 context 的問題，並要求 ChatGPT 對已排定且缺少獨立名稱來源的 Place ID 使用即時 `get_place_details`。既有行程原始檔未改寫；讀取與未來投影會套用清理。
- PR #244 讓未排入候選景點的 warning 不阻止發布。PR #245 允許只有可揭露 warning 的行程以 preview 公開；網站 bundle 保留 `warning`，registry readiness 保留 `incomplete`。錯誤級驗證、沒有任何餐點的日期與其他硬性缺項仍拒絕發布。
- PR #256 commit `0a27009a349a0040bdde1d54674684ae7a3d59b6` 的完整 pytest 通過：377 passed、288 subtests passed；CI 的 unittest、pytest、mcp-site 三項均成功。Railway deployment `f2400745-ddc7-4db3-a818-0022bacf9ed4` 使用 merge commit `3f7df71f93c33ca06c0daf866f0c6b3d562ee71d` 且狀態 `SUCCESS`，`/health` HTTP 200。
- 使用者提供的 ChatGPT Chat 正式規劃結果顯示倉敷五天每日有 2 至 3 筆餐點，共 11 筆；住宿留空。仍有 4 個未安排餐段、費用估算不完整 warning。Issue #180 原始「每日完全沒有餐點」問題已據此結案；這些 warning 仍須如實呈現。
- Issue #179 仍開啟。2026-10-08 已透過 AI Travel Planner MCP 將使用者明確核准的倉敷行程發布為 `preview`／`incomplete`。工具回 `publish_accepted`，Pages workflow `37736450625` 成功，目標 URL 與 `public-bundle.json` 回 HTTP 200，registry 狀態為 `preview`、readiness 為 `incomplete`。發布 commit `d40c71c84e94c201b5de8a5889fced98abdd250f` 的 Website CI `37736450517` 發現入口頁 E2E 將行程數量固定為 5；PR #250 改為依公開 registry 動態驗證數量，所有 PR CI 通過，並以 `8eec8baa2a7647a197b713cf9305fe71974409a8` 合併。合併後 CI `37737544356`、Website CI `37737544402` 與 Pages workflow `37737544370` 均成功。ChatGPT 一般 Chat UI 與互動式瀏覽器仍待驗，Computer Use 當時回報 macOS 已鎖定。
- Issue #179 仍開啟。正式 `get_trip` 唯讀仍回 10 個舊資料的候選警告、4 個缺少早餐餐段及 `budget.incomplete`；已核准行程的 `publish_trip_site` 回 `already_published`，網址存在且未覆寫，registry 為 `preview`／`incomplete`。這些歷史行程不會因 PR #256 自動重算；新的規劃只對可行備選項套用新警告分類。靜態頁顯示 Google Maps 泛用地點標籤；即時地點詳情和一般 ChatGPT Chat UI 驗收仍待完成。
- Issue #199 已依維護者指定範圍結案：新資料生命週期防線已部署；既有 Railway 行程、Pages 頁面與 Git 歷史保持原樣、不刪除或改寫。結案不表示歷史內容已清除、逐欄重新驗證或作出法律合規結論。
- 目前開啟的服務能力 issue 為 #179。一般 ChatGPT Chat prompt 仍由使用者本人輸入；目前 Computer Use 顯示 macOS 已鎖定且唯一 Chrome 分頁是 ai-video 對話，未進行錯誤分頁操作。
- 使用者已明確保留 ChatGPT 一般 Chat prompt 由本人輸入。沒有輸入或代送 prompt。已核准的發布動作已由正式 MCP 確認為 `already_published`；Pages URL 與公開資料 HTTP 200，但不能代替一般 ChatGPT Chat UI 和互動式瀏覽器驗收。Computer Use 最近可見唯一 Chrome 分頁是既有 ai-video ChatGPT 對話，macOS 鎖定。

## 更新規則

每次重要 merge 或正式驗收後，更新本文件基線與 [`ChatGPT MCP 正式環境現況`](mcp-production-status.md)，並更新對應 GitHub Issue。記錄 commit SHA、命令與結果、Railway deployment ID/status、實際 ChatGPT 工具名稱／結果、瀏覽器 URL／觀察；只記錄 secret 變數名稱，不記錄 secret 值。
