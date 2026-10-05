# ChatGPT MCP 正式環境現況與已知問題

最後查證：2026-10-05。本文記錄本 repo MCP 部署與實際規劃呼叫的觀察結果，不代表規劃品質已達可交付標準。

## ChatGPT 連線狀態

- 私人 ChatGPT Site 已連到此 repo 的 Railway MCP backend；使用者曾在自己的 ChatGPT chat 中選取並呼叫 AI Travel Planner MCP 工具。
- Railway backend origin：`https://ai-travel-planner-production-732b.up.railway.app`。
- MCP endpoint：`https://ai-travel-planner-production-732b.up.railway.app/mcp`。
- `/health` 的最近記錄驗證為 HTTP 200；未帶授權直接呼叫 `/mcp` 回 HTTP 401 是預期行為。
- Railway CLI 注入正式環境 `BEARER_TOKEN` 後，遠端 MCP `tools/list`、`parse_trip_request` 可回 HTTP 200。完整可重複命令見 [Railway 驗證紀錄](../.railway/README.md#正式服務網址與驗證)。
- 不在 repo、Issue 或文件記錄任何 secret 值。使用者在 ChatGPT 的工具呼叫驗收，仍由使用者本人於 chat 操作；其餘 backend 驗證由維護者執行。

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

## 尚待處理的 GitHub Issues

- [#153 遠端 ChatGPT MCP hosting 與連線](https://github.com/JackyTsai70113/ai-travel-planner/issues/153)：issue 尚未關閉；現有私人連線與使用者 chat 呼叫證據記錄於上方，剩餘 acceptance 仍需逐項核對。
- [#174 每日只有一個景點的 legacy fallback](https://github.com/JackyTsai70113/ai-travel-planner/issues/174)。
- [#175 Amadeus 退役後沒有可用住宿搜尋來源](https://github.com/JackyTsai70113/ai-travel-planner/issues/175)。
- [#176 不設預算上限卻標示 budget incomplete](https://github.com/JackyTsai70113/ai-travel-planner/issues/176)。
- [#177 YouTube timeout 與 research 穩定性](https://github.com/JackyTsai70113/ai-travel-planner/issues/177)。
- [#178 `plan_trip` 將有未完成階段的輸出標示為 complete](https://github.com/JackyTsai70113/ai-travel-planner/issues/178)。
- [#179 MCP 規劃結果沒有對應的 GitHub Pages 網址](https://github.com/JackyTsai70113/ai-travel-planner/issues/179)。
- [#180 餐廳候選沒有排入每日用餐行程](https://github.com/JackyTsai70113/ai-travel-planner/issues/180)。

以上 issues 記錄已觀察到的問題；尚未宣稱有解法，也沒有在本次變更中修改規劃器或發布倉敷頁面。
