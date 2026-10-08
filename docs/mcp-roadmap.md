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

- 私人 MCP 已連接 Railway `ai-traveller`；既有 ChatGPT Chat 曾成功呼叫 `parse_trip_request`。這證明 connector 路徑，不代表完整即時規劃成功。
- `plan_trip` 倉敷正式案例於 2026-10-05 仍有 20 筆餐廳候選、0 間住宿、每日 0 餐點；此為已知舊 production 證據。
- 住宿自動搜尋已由維護者放棄；住宿不是規劃必要欄位，可以空白。MCP 尚未把自由文字住宿名稱轉成 canonical lodging candidate。
- PR #214 以一般 merge 合併後，無住宿時的可行景點間餐點排程已加 regression。PR #215 以一般 merge 合併 `b067651`，補上 final Canonical Trip 保存排餐 warning 的 production composition regression。Railway 已部署 `b067651` 為 deployment `cb92a197-1ff9-4ec8-a79f-6e499b0d0f75`，狀態 `SUCCESS`。
- PR #215 的記錄測試證明合成路線資料可排三餐／兩餐及保留未排 warning，不代表新的 live 倉敷 MCP run 已成功。#180 在正式 ChatGPT 工具結果確認前保持開啟。
- Railway `GITHUB_TOKEN` 已存在，且唯讀 GitHub REST 檢查曾確認 repository push permission。沒有為驗收建立假行程公開頁；#179 仍待對已選定行程的明確公開確認、Pages 成功部署與瀏覽器核對。
- #199 發現 Google Places 顯示內容會流入 Canonical Trip、Railway HTML 與公開 bundle。Places 保存／公開條款及既有資料清理尚未完成；單加 attribution 或 30 日座標期限不足以解除。

## 更新規則

每次重要 merge 或正式驗收後，更新本文件基線與 [`ChatGPT MCP 正式環境現況`](mcp-production-status.md)，並更新對應 GitHub Issue。記錄 commit SHA、命令與結果、Railway deployment ID/status、實際 ChatGPT 工具名稱／結果、瀏覽器 URL／觀察；只記錄 secret 變數名稱，不記錄 secret 值。
