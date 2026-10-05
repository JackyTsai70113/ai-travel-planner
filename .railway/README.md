# Railway 部署設定

`.railway/railway.ts` 是本專案 Railway production 環境的 IaC 定義，管理 GitHub repo 來源、服務副本數、`/data` volume、Dockerfile、健康檢查、重啟策略及既有服務變數。

## 檢查與套用

安裝 repo 根目錄的 JavaScript 開發相依套件後，先預覽遠端與本機定義的差異：

```sh
npm install
railway config plan
```

確認 plan 沒有移除服務變數、解除 GitHub repo 來源或卸載 `/data` volume，且 Dockerfile 與部署設定正確後，才執行：

```sh
railway config apply
```

變數以 `preserve()` 表示保留 Railway 現有值，不將 secret 明文寫進 repo。新增或移除服務變數時，應先檢視 `config plan` 的實際差異。

## 重要設定

- 來源：`JackyTsai70113/ai-travel-planner`
- 建置：repo 根目錄的 `/Dockerfile`
- 健康檢查：`/health`，逾時 120 秒
- 重啟：失敗時重試，最多 10 次（與 Railway 目前服務設定一致）
- 永續資料：volume 掛載於 `/data`，服務維持單一副本

## 正式服務網址與驗證

2026-10-05 已查證 Railway production domain：

- 服務網址：`https://ai-travel-planner-production-732b.up.railway.app`
- 健康檢查端點：`https://ai-travel-planner-production-732b.up.railway.app/health`
- 後端 MCP endpoint：`https://ai-travel-planner-production-732b.up.railway.app/mcp`

健康端點實測回傳 HTTP 200 與 `ok`。未帶授權資料直接呼叫 `/mcp` 會回 HTTP 401，這是預期行為：後端要求 `BEARER_TOKEN` 與 Sites Worker 傳入的 `oai-authenticated-user-id`。Railway 的 IaC 已設定 `/health` 與 120 秒 timeout，但 plan 尚未 apply；端點本身目前已可正常回應。

以下只讀 smoke test 透過 Railway CLI 將 `BEARER_TOKEN` 注入子程序，不會印出 token；測試用識別值只用來模擬 Sites Worker 的必要標頭：

```sh
railway run --service ai-travel-planner --environment production -- node -e 'const r = await fetch("https://ai-travel-planner-production-732b.up.railway.app/mcp", {method:"POST", headers:{"Authorization":`Bearer ${process.env.BEARER_TOKEN}`, "oai-authenticated-user-id":"diagnostic-readonly-check", "Content-Type":"application/json", "Accept":"application/json, text/event-stream"}, body:JSON.stringify({jsonrpc:"2.0",id:1,method:"tools/list",params:{}})}); const body = await r.json(); console.log(JSON.stringify({httpStatus:r.status,tools:(body.result?.tools||[]).map(tool=>tool.name)}));'
```

已於 2026-10-05 在 PR #191 合併後重新實測：Railway deployment 狀態為 `SUCCESS`，`/health` 回 HTTP 200；`tools/list` 回 HTTP 200，列出 `parse_trip_request`、`validate_trip`、`get_trip`、`plan_trip`、`build_trip_site`、`publish_trip_site`。此次只做工具探索，沒有呼叫會公開行程的發布工具。實際 ChatGPT 使用者應透過私人 Site Worker 呼叫 MCP，不要把 Railway 後端網址當作公開的 Site Worker 網址。

也可直接透過後端唯讀測試 parser：

```sh
railway run --service ai-travel-planner --environment production -- node -e 'const r = await fetch("https://ai-travel-planner-production-732b.up.railway.app/mcp", {method:"POST", headers:{"Authorization":`Bearer ${process.env.BEARER_TOKEN}`, "oai-authenticated-user-id":"diagnostic-readonly-check", "Content-Type":"application/json", "Accept":"application/json, text/event-stream"}, body:JSON.stringify({jsonrpc:"2.0",id:2,method:"tools/call",params:{name:"parse_trip_request",arguments:{request:"我想安排倉敷五天四夜"}}})}); const body = await r.json(); const result = body.result?.structuredContent; console.log(JSON.stringify({httpStatus:r.status,status:result?.status,destinations:result?.intent?.destinations,duration_days:result?.intent?.duration_days,duration_nights:result?.intent?.duration_nights}));'
```

預期 HTTP 200，結果包含 `status: "parsed"`、`destinations: ["倉敷"]`、`duration_days: 5`、`duration_nights: 4`。

2026-10-05 也以實際的完整需求執行 `parse_trip_request`：

```text
日本岡山縣倉敷五天四夜。日期：2026/11/01～2026/11/05。出發地：桃園國際機場。旅客：6位成人、1位2歲幼兒。預算：暫不設限制。交通方式：自駕。
```

結果為倉敷、岡山縣、2026-11-01 至 2026-11-05、5 天 4 夜、桃園、6 位成人與 1 位 2 歲幼兒、預算不限、自駕，`missing_fields` 與 `ambiguous_fields` 都是空陣列。以相同需求呼叫 `plan_trip` 並設定 `confirm_write=false`，實測回傳 `confirmation_required`；這是無寫入的安全檢查，不會開始 provider research 或建立行程檔案。

之後的 repo 驗證由維護者直接執行上述 health 與 MCP smoke test，並檢查工具回應；只有 ChatGPT 對話中的 prompt 驗收需要 ChatGPT 使用者操作，不要把 curl 或後端 smoke test 留給使用者代跑。


### GitHub Pages 發布工具狀態

`publish_trip_site` 已部署並出現在遠端 `tools/list`。發布前會要求 ChatGPT 使用者明確確認公開；多日行程必須有對應到實際 hotel candidate 的住宿，每日都須有餐點，日期必須有效，Canonical Trip validation 也不可有 findings。相同 bundle 的 registry 缺項或過期時，工具只修復 registry。

2026-10-05 已用 `railway variable list` 只輸出變數名稱核對正式服務設定，沒有讀取或列印 secret 值。清單尚無 `GITHUB_TOKEN`，因此未執行真實 Pages 發布，Issue #179 仍待維護者設定最小權限 fine-grained PAT，並在 ChatGPT 明確要求公開後完成部署與網址驗證。
