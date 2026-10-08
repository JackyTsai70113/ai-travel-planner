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

- Railway 專案：`ai-traveller`。服務與 `/data` volume：`ai-traveller`、`ai-traveller-volume`。
- GitHub 來源 repo：`JackyTsai70113/ai-travel-planner`（repo 名稱保持不變）。
- 建置：repo 根目錄的 `/Dockerfile`
- 自動部署監看：`Dockerfile`、`requirements-mcp.txt`、`requirements-mcp-server.txt`、`src/**`、`trips/**`。只修改網站、測試或文件時略過 Railway 後端部署；IaC 設定檔的變更仍須由維護者執行 `railway config plan` 並檢查後 `railway config apply`。
- 健康檢查：`/health`，逾時 120 秒
- 重啟：失敗時重試，最多 10 次（與 Railway 目前服務設定一致）
- 永續資料：volume 掛載於 `/data`，服務維持單一副本

## 正式服務網址與驗證

2026-10-07 Railway project、service、volume 與 Railway 提供的 service domain 已改名為 `ai-traveller` 系列，並確認 service、volume 與 Site MCP 仍可用：

- 服務網址：`https://ai-traveller-production-732b.up.railway.app`
- 健康檢查端點：`https://ai-traveller-production-732b.up.railway.app/health`
- 後端 MCP endpoint：`https://ai-traveller-production-732b.up.railway.app/mcp`

改名後因舊 deployment 的 Host allowlist 暫時回 HTTP 421；重新部署後已恢復。2026-10-08 核對 production deployment `a9a03231-37f2-46cc-8a15-4cdc379f7224` 為 `SUCCESS`，source commit 為 `62ae026ce9f55b2a7a39bc24f95ec7a4130c63b0`，服務設定含 DOCKERFILE `/Dockerfile`、`/health`（120 秒）、失敗重啟最多 10 次，`/data` volume 仍掛載。部署完成後 `/health` 回 HTTP 200 與 `ok`。移除 IaC 中明確重複的預設重啟政策後，`railway config plan` 回報 `Your Railway configuration is already up to date.`；這不改變 Railway 已使用的 On Failure、10 次重試預設。帶有效 `BEARER_TOKEN` 的 MCP 呼叫列出 6 個工具；私人 ChatGPT Site 中的 `parse_trip_request` 也已在部署後實際成功。

以下只讀 smoke test 透過 Railway CLI 將 `BEARER_TOKEN` 注入子程序，不會印出 token；測試用識別值只用來模擬 Sites Worker 的必要標頭：

```sh
railway run --service ai-traveller --environment production -- node -e 'const r = await fetch("https://ai-traveller-production-732b.up.railway.app/mcp", {method:"POST", headers:{"Authorization":`Bearer ${process.env.BEARER_TOKEN}`, "oai-authenticated-user-id":"diagnostic-readonly-check", "Content-Type":"application/json", "Accept":"application/json, text/event-stream"}, body:JSON.stringify({jsonrpc:"2.0",id:1,method:"tools/list",params:{}})}); const body = await r.json(); console.log(JSON.stringify({httpStatus:r.status,tools:(body.result?.tools||[]).map(tool=>tool.name)}));'
```

已於 2026-10-08 重驗：Railway deployment 狀態為 `SUCCESS`，`/health` 回 HTTP 200；先前的 `tools/list` 回 HTTP 200，列出 `parse_trip_request`、`validate_trip`、`get_trip`、`plan_trip`、`build_trip_site`、`publish_trip_site`。部署後再由 ChatGPT Chat 對私人 Site 呼叫 `parse_trip_request`，實際得到倉敷、5 天 4 夜的解析結果。此次沒有呼叫會寫入或公開行程的工具。實際 ChatGPT 使用者應透過私人 Site Worker 呼叫 MCP，不要把 Railway 後端網址當作公開的 Site Worker 網址。

也可直接透過後端唯讀測試 parser：

```sh
railway run --service ai-traveller --environment production -- node -e 'const r = await fetch("https://ai-traveller-production-732b.up.railway.app/mcp", {method:"POST", headers:{"Authorization":`Bearer ${process.env.BEARER_TOKEN}`, "oai-authenticated-user-id":"diagnostic-readonly-check", "Content-Type":"application/json", "Accept":"application/json, text/event-stream"}, body:JSON.stringify({jsonrpc:"2.0",id:2,method:"tools/call",params:{name:"parse_trip_request",arguments:{request:"我想安排倉敷五天四夜"}}})}); const body = await r.json(); const result = body.result?.structuredContent; console.log(JSON.stringify({httpStatus:r.status,status:result?.status,destinations:result?.intent?.destinations,duration_days:result?.intent?.duration_days,duration_nights:result?.intent?.duration_nights}));'
```

預期 HTTP 200，結果包含 `status: "parsed"`、`destinations: ["倉敷"]`、`duration_days: 5`、`duration_nights: 4`。

2026-10-05 也以實際的完整需求執行 `parse_trip_request`：

```text
日本岡山縣倉敷五天四夜。日期：2026/11/01～2026/11/05。出發地：桃園國際機場。旅客：6位成人、1位2歲幼兒。預算：暫不設限制。交通方式：自駕。
```

結果為倉敷、岡山縣、2026-11-01 至 2026-11-05、5 天 4 夜、桃園、6 位成人與 1 位 2 歲幼兒、預算不限、自駕，`missing_fields` 與 `ambiguous_fields` 都是空陣列。以相同需求呼叫 `plan_trip` 並設定 `confirm_write=false`，實測回傳 `confirmation_required`；這是無寫入的安全檢查，不會開始 provider research 或建立行程檔案。

之後的 repo 驗證由維護者直接執行上述 health 與 MCP smoke test，並檢查工具回應；只有 ChatGPT 對話中的 prompt 驗收需要 ChatGPT 使用者操作，不要把 curl 或後端 smoke test 留給使用者代跑。

### GitHub Pages 發布工具狀態

`publish_trip_site` 已部署並出現在遠端 `tools/list`。發布前會要求 ChatGPT 使用者明確確認公開；每一天都必須有餐點，日期必須有效，Canonical Trip validation 不可有阻擋 finding，Google Places provenance 也會阻止內容寫入 Pages bundle。住宿可以留空；未提供住宿時，`schedule.hotel_missing` 和 `schedule.origin_unknown` 會保留為未驗證警告，不會因缺住宿本身阻擋發布。相同 bundle 的 registry 缺項或過期時，工具只修復 registry。

截至 2026-10-08，Railway production `GITHUB_TOKEN` 已存在；正式執行個體以 GitHub REST 唯讀查詢確認 repo 為 `JackyTsai70113/ai-travel-planner` 且回報 `permissions.push=true`，過程沒有輸出 token。PR #230 合併後，Railway deployment `522e831d-be9b-4dd4-aa75-d016b6ec058d` 使用 main commit `fe0ae02047c05488a2cafb03f37bc646add6cf67`，狀態 `SUCCESS`，service Online，health 回 HTTP 200。`railway config plan` 套用後為 no-op；MCP 後端唯讀 `tools/list` 列出六項工具，`parse_trip_request` 正確解析倉敷五天四夜。這些後端 smoke tests 不等於 ChatGPT Chat UI 驗收。尚未執行真實 Pages 發布；#179 仍待符合發布 readiness 的行程、ChatGPT 明確公開指令及正式網址驗收。若行程含 Google Places provenance，現有發布 guard 會回 `not_ready`，相關資料生命週期追蹤於 #199。

2026-10-05 的歷史檢查當時尚無 `GITHUB_TOKEN`；其後的設定與權限驗證以本節 2026-10-08 狀態為準。

只核對變數名稱且不顯示值的指令：

```sh
railway variable list --service ai-traveller --environment production --json | jq -r 'if type == "array" then .[] | if type == "object" then ((.name // .key) | strings) else empty end else keys[] end' | sort
```
