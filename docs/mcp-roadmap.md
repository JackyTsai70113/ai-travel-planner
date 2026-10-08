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

- 最新 main 為 PR #236 的文件 merge commit `72d0dbf196c1e6ffc048cd75194c9f829439b65b`；最近一次影響後端的 commit 是 PR #235 merge commit `9219ffbda35d82d547324038e0f47cfdc5178659`。Railway production deployment `90208905-5cea-46a9-bf2a-eb8b4aa9f11f` 使用後者、狀態 `SUCCESS`；`/health` HTTP 200，MCP `tools/list` HTTP 200 並列出 7 個工具，含 `get_place_details`。
- Railway CLI 的唯讀 MCP 驗證確認 `get_place_details` 即時查詢成功。另以 production `parse_trip_request` 解析完整倉敷需求，回 HTTP 200、目的地倉敷、岡山縣、2026-11-01 至 2026-11-05、6 位成人、1 位 2 歲幼兒、不限預算、`missing_fields=[]`。這些是 Railway endpoint 證據，不等於 ChatGPT Chat UI 驗收。
- ChatGPT 一般 Chat 過去曾成功呼叫 `parse_trip_request`。本次 Computer Use 回報 macOS 已鎖定，未輸入或代送 prompt；目前最新版本的 ChatGPT UI 工具發現與呼叫仍未驗收。
- `plan_trip` 倉敷舊正式案例（2026-10-05）有 20 筆餐廳候選、每日 0 餐點。後續 #214/#215 已加入無住宿時的可行景點間排餐與 production composition regressions；仍須以維護者在一般 ChatGPT Chat 新發起的真實規劃結果驗證，不把舊 Trip 或 mock 測試當成最新行為證據。自動住宿搜尋已放棄，住宿可留空或由旅客提供。
- #179 的 publisher 已部署；`GITHUB_TOKEN` 存在且先前唯讀 GitHub REST 查詢確認 repo `permissions.push=true`。沒有建立假行程公開頁。仍須由使用者指定並明確確認真正要公開的行程，再驗證 Pages 部署和結果網址。
- PR #235 為 #199 實作 Place ID 持久化、Google Places 詳細資料請求時查詢、資料投影、署名、失敗處理和回歸測試。既有 Railway 檔案、已發布靜態頁與 Git 歷史依維護者要求未刪除或改寫；#199 因舊公開資料處置仍開啟。
- 目前開啟的服務能力 issues 為 #180（新的正式 `plan_trip` 餐點驗收）、#179（明確授權的 Pages 真實發布驗收）、#199（既有公開歷史資料處置）。

## 更新規則

每次重要 merge 或正式驗收後，更新本文件基線與 [`ChatGPT MCP 正式環境現況`](mcp-production-status.md)，並更新對應 GitHub Issue。記錄 commit SHA、命令與結果、Railway deployment ID/status、實際 ChatGPT 工具名稱／結果、瀏覽器 URL／觀察；只記錄 secret 變數名稱，不記錄 secret 值。
