# ChatGPT MCP 正式環境現況與已知問題

最後查證：2026-10-08。本文記錄本 repo MCP 部署與實際工具呼叫的觀察結果，不代表規劃品質已達可交付標準。

## 2026-10-08 本輪重驗

- ChatGPT Chat 使用已連線的私人 `AI Travel Planner MCP` 呼叫 `parse_trip_request`，輸入「岡山縣倉敷五天四夜，6 位成人、1 位 2 歲幼兒，預算不設限制」。回應解析出目的地倉敷、區域岡山縣、5 天 4 夜、6 位成人、1 位 2 歲幼兒、`budget_status=unlimited`，`missing_fields=[]`。此為唯讀呼叫，未執行研究、寫入或公開行程。
- Railway OAuth connector 對正式 project `ai-traveller` / `production` 以遮蔽值模式列出變數名稱。已存在 `BEARER_TOKEN`、`GOOGLE_MAPS_API_KEY`、`OPENROUTESERVICE_API_KEY`、`PUBLIC_URL`、`YOUTUBE_API_KEY`；沒有 `GITHUB_TOKEN`。沒有讀取任何 secret 值。
- PR #204 已合併至 `8fbe0639d5fd341cbcc764979ff9e19cae30c6c2`，CI、Website CI、GitHub Pages deploy 均成功。首次檢視舊分頁仍顯示舊內容；強制重新載入後，GitHub Pages 首頁顯示新文案「頁面公開狀態與行程完成度分開呈現；公開預覽不代表行程已確認。」及「公開預覽」狀態。這只驗證公開目錄標籤，沒有改動或發布任何行程。
- 四張仍開啟 issue 的最新外部依賴：#175 沒有已核准住宿庫存供應商；#179 沒有 Railway `GITHUB_TOKEN`；#180 的真實倉敷紀錄沒有可選住宿，無法驗證每日餐點往返路線；#199 的 Places 資料生命週期與網站條款／歸屬標示仍未完成確認。四張均不能以本輪唯讀解析驗收當作完成。

## ChatGPT 連線狀態

- 私人 ChatGPT Site 已連到此 repo 的 Railway MCP backend；使用者曾在自己的 ChatGPT chat 中選取並呼叫 AI Travel Planner MCP 工具。
- Railway backend origin：`https://ai-traveller-production-732b.up.railway.app`。
- MCP endpoint：`https://ai-traveller-production-732b.up.railway.app/mcp`。
- `/health` 的最近記錄驗證為 HTTP 200；未帶授權直接呼叫 `/mcp` 回 HTTP 401 是預期行為。
- 2026-10-08 部署紀錄：Railway deployment `a9a03231-37f2-46cc-8a15-4cdc379f7224` 為 `SUCCESS`，source commit 為 `62ae026ce9f55b2a7a39bc24f95ec7a4130c63b0`；replica 為 Online，Dockerfile 為 `/Dockerfile`、healthcheck 為 `/health`、volume 掛載在 `/data`。部署後正式 `/health` 回 HTTP 200、內文 `ok`。該部署 manifest 確認 Railway 實際使用 On Failure、10 次重試；IaC 移除與 Railway 預設重複的明確覆寫後，`railway config plan` 回報無變更。完整驗證方式見 [Railway 驗證紀錄](../.railway/README.md#正式服務網址與驗證)。
- 2026-10-08 部署後使用 Computer Use 在 ChatGPT Chat 以外掛選單明確選取私人 `AI Travel Planner MCP`，使用者訊息顯示該 Site 連結，並要求只呼叫 `parse_trip_request`。實際回應 `status=parsed`、目的地倉敷、5 天 4 夜，且列出未提供旅客人數與預算。另一次唯讀呼叫 `publish_trip_site` 傳入測試 trip ID 與 `confirm_public_publish=false`，回傳 `status=confirmation_required`；沒有讀取行程檔、執行 `plan_trip` 或公開發布。瀏覽器操作前已核對 Chrome、ChatGPT 對話網址／標題及 AI Travel Planner MCP 名稱，操作後確認結果出現在同一對話。
- 同日只列出 Railway 正式服務變數名稱以確認缺漏，未讀取或輸出 secret 值；清單沒有 `GITHUB_TOKEN`。尚未執行任何公開行程寫入。
- 不在 repo、Issue 或文件記錄任何 secret 值。ChatGPT Chat 呼叫由維護者使用已連線的使用者環境實際執行；其餘 backend 驗證亦由維護者執行。

## Provider 實測

- Google Places API (New)：Railway 正式環境以倉敷查詢回 HTTP 200，取得 18 筆 place ID。此前曾有 HTTP 403 `PERMISSION_DENIED`；2026-10-05 重測已可用。文件不保存 API key，也不宣稱取得的結果就是使用者 GCP 畫面中的完整 key 字串比對結果。
- YouTube Data API：獨立 smoke test 曾回 HTTP 200、3 筆影片；實際 `plan_trip` 當次研究出現 TLS handshake timeout。因此，單次成功 smoke test 不代表每次 production research 都穩定。
- 住宿搜尋：production 回報 Amadeus Self-Service 已退役且沒有 replacement provider；此 run 沒有住宿候選。
- Google Flights 僅提供搜尋連結、不擷取票價；倉敷輸出含「桃園 → 倉敷」的 Google Flights 搜尋連結。`candidate_sets.flights` 為空是目前設計，不代表行程沒有航班搜尋入口。

## 倉敷 production run 證據

輸入：日本岡山縣倉敷，2026-11-01 至 2026-11-05，6 位成人、1 位 2 歲幼兒，預算不設上限，自駕，出發地桃園國際機場；trip ID `kurashiki-2026-11`。

2026-10-05 對正式 MCP 呼叫 `plan_trip(confirm_write=true)` 後的觀察：

- MCP HTTP 200，工具最上層回 `status=complete`。
- Canonical Trip 通過 Trip V1 schema validation；日期、旅客資料與 Google Flights 搜尋連結存在。
- 五天每日各只有一筆 `visit` 景點，沒有餐點或餐廳行程項目。
- 研究候選集合有 20 筆餐廳、40 筆景點、0 筆住宿；沒有選定住宿。
- `research` 與 `validator_repair` stage 回報 `incomplete`。警告包括 YouTube timeout、住宿搜尋不可用、五個景點營業時間未確認，以及 `budget.incomplete`。
- 使用者明確表示預算不設上限，但該 Canonical Trip 的總額仍為 JPY 0、狀態 `incomplete`。
- Railway volume 有 `/data/trips/kurashiki-2026-11/trip.json` 和 `/data/site/kurashiki-2026-11/index.html`。
- Railway HTML 已有 Google Flights 連結；它不是 GitHub Pages 上可分享的行程頁。
- repo `web/public/trip-registry.json` 和 `web/public/trips/requested/` 沒有此 trip，因此目前沒有對應的 GitHub Pages 網址。

本次輸出暴露「頂層 complete 與未完成 stage/內容並存」的狀態問題。不可只憑 `status=complete` 宣稱行程完整。

## 目前開啟的 Issues 與可推進範圍

以下狀態已於 2026-10-08 依 GitHub issue list 和正式環境證據核對：

- [#153 遠端 ChatGPT MCP hosting 與連線](https://github.com/JackyTsai70113/ai-travel-planner/issues/153)：已關閉；Railway backend 與私人 ChatGPT Site 的工具呼叫已實際成功。這不代表完整行程規劃功能已全部驗收。
- [#175 Amadeus 退役後沒有可用住宿搜尋來源](https://github.com/JackyTsai70113/ai-travel-planner/issues/175)：目前沒有已核准的 lodging inventory provider 或 partner credentials。Google Places 不提供日期型房間 availability 與住宿總價。未取得合法供應商存取前，無法完成真實住宿候選的 acceptance。
- [#180 餐廳候選沒有排入每日用餐行程](https://github.com/JackyTsai70113/ai-travel-planner/issues/180)：production run 有 20 筆餐廳候選，但無可選住宿；目前每日往返住宿路線無法驗證，因此不可把餐廳硬塞進日程。需有住宿候選後重跑真實情境。
- [#179 MCP 規劃結果沒有對應的 GitHub Pages 網址](https://github.com/JackyTsai70113/ai-travel-planner/issues/179)：PR #189、#191 已加入並部署 `publish_trip_site` 與發布 readiness gate。2026-10-08 正式環境變數名稱清單仍沒有 `GITHUB_TOKEN`，也未執行真實 Pages 發布，因此 issue 保持開啟。
- [#199 Google Places 資料保存與公開展示政策待確認](https://github.com/JackyTsai70113/ai-travel-planner/issues/199)：Places provider facts 進入可持久化 Canonical Trip；Google 官方政策對資料保存、條款／隱私揭露與 attribution 有要求。repo 尚未完成資料生命週期與網站呈現的合規盤點，因此不能宣稱目前 Places 使用方式已確認符合政策。

### Issue #179 驗收流程

1. 維護者在 GitHub 建立 fine-grained PAT，只授權 `JackyTsai70113/ai-travel-planner` repository 的 `Contents: Read and write`，將其設為 Railway service secret `GITHUB_TOKEN`。目前缺少此變數；不得將 token 寫入 repo、issue、聊天工具參數或 CI log。
2. 確認 Railway 使用至少包含 PR #191 merge commit `0a948bcfb8dcb6089e9f1daf16adad1e469b1b15` 的版本，且最新 deployment 狀態為 `SUCCESS`；新增 secret 後等新 deployment 成功，再由維護者重跑 health 與 `tools/list` smoke test。
3. 在 ChatGPT chat 先完成行程規劃。只有使用者明確要求公開分享並確認公開範圍後，才呼叫 `publish_trip_site`，傳入既有 `trip_id`、`confirm_public_publish=true`；更新現有公開內容時還要明確傳 `confirm_overwrite=true`。
4. 工具回傳 `publish_accepted` 與 Pages URL 後，等待 Pages Actions 部署完成，實際開啟網址確認對應行程內容。僅工具接受寫入或回 `pending` 不算完成驗收。
5. 將 deployment 結果、HTTP/瀏覽器可用證據與 commit SHA 記錄回 #179；驗收全部完成後才關閉 issue。

以上只列已觀察問題與外部依賴，不宣稱 #175/#180 已解決；本次沒有以 fixture 代替正式資料，也沒有發布倉敷頁面。
