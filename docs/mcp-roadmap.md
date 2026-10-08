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

## 目前基線（2026-10-08）

- `main` 為 `49ea552ff962c8bb15404040422632526fbf0e1f`。PR #243、#244、#245 以一般 merge 合併；補充工具描述與文件的 `49ea552` 是直接推送至 `main` 的一般 commit，沒有經 PR。其 GitHub Actions CI run `37735337661` 的 `python`、`pytest`、`mcp-site` 均成功。
- Railway `ai-traveller` production deployment `c8dfaf4f-3549-4a74-a269-679f431c57a9` 對應目前 `main` SHA，狀態 `SUCCESS`；正式 `/health` 回 `ok`。
- PR #243 修正持久化／發布投影中 Google Places 候選驗證訊息殘留名稱與 context 的問題，並要求 ChatGPT 對已排定且缺少獨立名稱來源的 Place ID 使用即時 `get_place_details`。既有行程原始檔未改寫；讀取與未來投影會套用清理。
- PR #244 讓未排入候選景點的 warning 不阻止發布。PR #245 允許只有可揭露 warning 的行程以 preview 公開；網站 bundle 保留 `warning`，registry readiness 保留 `incomplete`。錯誤級驗證、沒有任何餐點的日期與其他硬性缺項仍拒絕發布。
- 本機全套 pytest：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/ai-travel-mcp-current-venv/bin/python -m pytest -q`，375 passed、288 subtests passed。正式 deployment 亦通過 health check。
- 使用者提供的 ChatGPT Chat 正式規劃結果顯示倉敷五天每日有 2 至 3 筆餐點，共 11 筆；住宿留空。仍有 4 個未安排餐段、費用估算不完整 warning。Issue #180 原始「每日完全沒有餐點」問題已據此結案；這些 warning 仍須如實呈現。
- Issue #179 仍開啟。倉敷行程現可發布為 `preview`／`incomplete`；正式 production readiness 計算結果沒有硬性 blocker，但尚未執行真實 GitHub Pages 發布，也沒有最終網址及瀏覽器驗收。
- Issue #199 重新開啟。新資料的持久化與發布 projection 已清理候選詳情，但既有 Railway 行程及公開頁仍保持原狀；依維護者要求不刪除或改寫歷史資料。舊內容範圍仍待處置。
- 目前開啟的服務能力 issues 為 #179 與 #199。
- 使用者已明確保留 ChatGPT 一般 Chat prompt 由本人輸入。Computer Use 最近可見唯一 Chrome 分頁是既有 ChatGPT Chat，但 macOS 鎖定；沒有輸入或代送 prompt。部署健康、CI、單元測試與 Railway readiness 計算均不能代替使用者在 ChatGPT 發布行程，再由瀏覽器驗收 Pages 網址。

## 更新規則

每次重要 merge 或正式驗收後，更新本文件基線與 [`ChatGPT MCP 正式環境現況`](mcp-production-status.md)，並更新對應 GitHub Issue。記錄 commit SHA、命令與結果、Railway deployment ID/status、實際 ChatGPT 工具名稱／結果、瀏覽器 URL／觀察；只記錄 secret 變數名稱，不記錄 secret 值。
