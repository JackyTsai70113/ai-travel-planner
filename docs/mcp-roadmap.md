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

## 最新正式環境與一般 Chat 檢查（2026-10-09）

- Railway production deployment `aa3ef82c-f4ec-401d-9417-9d6e1aba59aa` 為 `SUCCESS`，source commit `530144f23546776088975f796e3cc2c18d1f8641`（PR #265 merge commit）。後續 main 只有倉敷公開行程投影與驗收文件變更，未改動 Railway 監看的 backend source。`/health` 回 HTTP 200／`ok`；透過 Railway CLI 注入環境變數但不輸出值，正式 `tools/list` 回 HTTP 200 並列出七項工具：`parse_trip_request`、`validate_trip`、`get_trip`、`get_place_details`、`plan_trip`、`build_trip_site`、`publish_trip_site`。
- 2026-10-09 使用 AI Travel Planner MCP 明確覆寫既有倉敷公開行程。`publish_trip_site` 回 `publish_accepted`，commit `4380781d3cf91cd41656176769b2c2403feb03c6`；Pages workflow `37832158960` 成功。使用同一個 Chrome 視窗實際打開公開頁與 D1，看到即時載入的 `大原美術館`、`Caty Cafe`、`大橋家住宅` 等名稱，以及 Google Maps 標示。公開 bundle 有 `place_details_api_base_url` 和 Place ID，未持久化 Google 地點名稱。此次只更新公開投影，未改寫行程內容；行程仍標示住宿與費用未完成。
- 一般 ChatGPT Chat 的外掛清單及選取器中均可見 `AI Travel Planner MCP`；外掛設定頁顯示 OAuth 與 `/mcp` endpoint。按下「重新整理工具」後按鈕持續 disabled，畫面沒有完成或失敗提示。新的一般 Chat composer 已選取 MCP，保持空白；沒有代替維護者輸入或送出 prompt，也未觀察到實際 ChatGPT MCP 工具呼叫。因此 #179 的一般 Chat 呼叫驗收仍未通過。

## 歷史基線（2026-10-09，合併 PR #265 前）

- Railway MCP runtime source SHA 為 `5b2b003c16201564bcda55edcccbb6d3e5948976`，deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 狀態 `SUCCESS`；正式服務 Online，`/health` 回 HTTP 200、內文 `ok`。正式後端此前 `tools/list` 回 HTTP 200、7 個工具。
- 2026-10-08 以 Railway CLI 再次核對七項工具，並對已排定 Place ID 呼叫一次 `get_place_details`；正式工具回 HTTP 200、`available`、`Google Maps` attribution。此 Codex connector 快照只有六項工具，缺少 `get_place_details`；此差異不代表 ChatGPT Chat 的工具清單。OpenAI 自訂 MCP plugin 文件指出 app 詳細資料頁可 Refresh apps 取得更新的工具描述和 server instructions；ChatGPT Chat 實際刷新與呼叫仍待驗收，詳細程序見[上線驗收流程](chatgpt-mcp-live-verification.md)。
- 2026-10-09 以 Railway CLI 核對正式服務 Online、deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 為 `SUCCESS`、source commit `5b2b003c16201564bcda55edcccbb6d3e5948976`；`/health` 回 HTTP 200，正式 `tools/list` 回 HTTP 200 並列出七項工具。`main` 的 `98ee35a` 後續變更僅為文件，Railway 對這些 commit 回報 `SKIPPED`（no changes to watched files）。
- 2026-10-09 使用 Computer Use 在一般 ChatGPT「對話」模式確認私人 `AI Travel Planner MCP` 出現在已安裝外掛清單、設定頁顯示 OAuth 與 `/mcp` endpoint，並可由一般 Chat 的外掛選單選取。外掛設定頁的「重新整理工具」按鈕被點擊後呈 disabled，畫面沒有成功或失敗通知；不可據此宣稱工具快照已刷新。一般 Chat 的新對話 composer 現留有未送出的 `AI Travel Planner MCP` 外掛標籤，尚未輸入或送出 prompt，亦未看到 MCP tool call 或工具回應。一般 Chat 的實際工具呼叫仍須由維護者本人輸入 [`ChatGPT Chat 驗收流程`](chatgpt-mcp-live-verification.md) 所列唯讀 prompt。
- 2026-10-09 本機命令 `PYTHONPATH=. uv run --isolated --with-requirements requirements-mcp.txt python -m unittest tests.test_mcp_server -v` 通過 21 項，含 stdio 子程序及 Streamable HTTP 驗證。測試與 Railway HTTP 檢查都不取代一般 ChatGPT Chat UI 的真實 MCP 工具呼叫。
- PR #243 至 #258 已以一般 merge 合併。PR #250 修正網站 E2E 將行程卡數寫死為 5 的回歸；PR #252 更新 `get_trip` 與 `get_place_details` 的工具說明；PR #256 修正可排入但未被選中的景點備選項不再造成未驗證警告；PR #258 在住宿留空時將首個景點最早排至 09:30，為早餐後已驗證路線保留 30 分鐘。
- PR #243 修正持久化／發布投影中 Google Places 候選驗證訊息殘留名稱與 context 的問題，並要求 ChatGPT 對已排定且缺少獨立名稱來源的 Place ID 使用即時 `get_place_details`。既有行程原始檔未改寫；讀取與未來投影會套用清理。
- PR #244 讓未排入候選景點的 warning 不阻止發布。PR #245 允許只有可揭露 warning 的行程以 preview 公開；網站 bundle 保留 `warning`，registry readiness 保留 `incomplete`。錯誤級驗證、沒有任何餐點的日期與其他硬性缺項仍拒絕發布。
- PR #258 commit `ce3a5f5` 的完整 pytest 通過：377 passed、288 subtests passed；CI 的 unittest、pytest、mcp-site 三項均成功。Railway deployment `549c1e92-161c-46f2-9552-cc2ea1605872` 使用 merge commit `5b2b003c16201564bcda55edcccbb6d3e5948976` 且狀態 `SUCCESS`，`/health` HTTP 200。No-lodging recorded provider fixture 排入 5 天早餐、午餐、晚餐，路線與營業時間驗證仍有效。
- 使用者提供的 ChatGPT Chat 正式規劃結果顯示倉敷五天每日有 2 至 3 筆餐點，共 11 筆；住宿留空。仍有 4 個未安排餐段、費用估算不完整 warning。Issue #180 原始「每日完全沒有餐點」問題已據此結案；這些 warning 仍須如實呈現。
- Issue #179 仍開啟。2026-10-08 已透過 AI Travel Planner MCP 將使用者明確核准的倉敷行程發布為 `preview`／`incomplete`。覆寫後公開頁的 Pages workflow `37742158112` 成功，頁面、bundle 與 registry 均已驗證。2026-10-09 一般 ChatGPT UI 已證明私人外掛已安裝且可選取；真正的 `parse_trip_request` 工具呼叫和公開行程頁的互動式瀏覽器檢查仍未完成。未代替維護者輸入或送出 prompt。
- Issue #179 仍開啟。維護者明確確認覆寫後，正式 MCP 成功發布重規劃版本：每天早餐、午餐、晚餐均已排入，共 15 餐；仍保留 3 個未排 POI 候選、5 個住宿／起點未知警告、`schedule.hotel_missing` 和 `budget.incomplete`。GitHub Pages workflow `37742158112` 成功，行程頁與 bundle 回 HTTP 200，registry 為 `preview`／`incomplete`。一般 ChatGPT Chat 工具刷新／呼叫及互動瀏覽器視覺驗收待完成；本次 Computer Use 因 macOS 鎖定且唯一 Chrome 分頁為 ai-video 對話，未操作該分頁。
- Issue #199 已依維護者指定範圍結案：新資料生命週期防線已部署；既有 Railway 行程、Pages 頁面與 Git 歷史保持原樣、不刪除或改寫。結案不表示歷史內容已清除、逐欄重新驗證或作出法律合規結論。
- 目前唯一開啟的服務能力 issue 為 #179。2026-10-09 已在一般 ChatGPT「對話」模式確認私人 MCP 已安裝且可選取，並將其標籤留在空白 composer；尚未輸入 prompt 或完成實際 MCP 呼叫。公開行程頁的互動式瀏覽器檢查也待完成。維護者明確要求由本人輸入驗收 prompt。
- 使用者已明確保留 ChatGPT 一般 Chat prompt 由本人輸入。2026-10-09 已在同一個 Chrome 視窗開啟新的 ChatGPT 一般 Chat，確認對話模式，並在 composer 選取 `AI Travel Planner MCP`；未輸入或代送 prompt。公開 URL 與 bundle 已 HTTP 驗證，但互動式頁面檢查及一般 Chat 真實工具呼叫仍未完成。

## 更新規則

每次重要 merge 或正式驗收後，更新本文件基線與 [`ChatGPT MCP 正式環境現況`](mcp-production-status.md)，並更新對應 GitHub Issue。記錄 commit SHA、命令與結果、Railway deployment ID/status、實際 ChatGPT 工具名稱／結果、瀏覽器 URL／觀察；只記錄 secret 變數名稱，不記錄 secret 值。
