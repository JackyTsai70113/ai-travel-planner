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

改名後因舊 deployment 的 Host allowlist 暫時回 HTTP 421；重新部署後已恢復。2026-10-08 最新核對的 production deployment `a28ae4e8-9811-4b3c-b108-3577390e3423` 為 `SUCCESS`，source commit 為 `08236f8cee5575bdad5d6930896fdb038cf9241e`，服務設定含 DOCKERFILE `/Dockerfile`、`/health`（120 秒）、失敗重啟最多 10 次，`/data` volume 仍掛載。部署完成後 `/health` 回 HTTP 200 與 `ok`。移除 IaC 中明確重複的預設重啟政策後，`railway config plan` 回報 `Your Railway configuration is already up to date.`；這不改變 Railway 已使用的 On Failure、10 次重試預設。正式 `tools/list` 回 HTTP 200，列出 7 個工具；`get_place_details` 對已排定 Place ID 的唯讀查詢回 `available` 並附 `Google Maps` attribution。

以下只讀 smoke test 透過 Railway CLI 將 `BEARER_TOKEN` 注入子程序，不會印出 token；測試用識別值只用來模擬 Sites Worker 的必要標頭：

```sh
railway run --service ai-traveller --environment production -- node -e 'const r = await fetch("https://ai-traveller-production-732b.up.railway.app/mcp", {method:"POST", headers:{"Authorization":`Bearer ${process.env.BEARER_TOKEN}`, "oai-authenticated-user-id":"diagnostic-readonly-check", "Content-Type":"application/json", "Accept":"application/json, text/event-stream"}, body:JSON.stringify({jsonrpc:"2.0",id:1,method:"tools/list",params:{}})}); const body = await r.json(); console.log(JSON.stringify({httpStatus:r.status,tools:(body.result?.tools||[]).map(tool=>tool.name)}));'
```

已於 2026-10-08 以最新 production runtime 重驗：Railway deployment `a28ae4e8-9811-4b3c-b108-3577390e3423` 狀態為 `SUCCESS`，source commit `08236f8cee5575bdad5d6930896fdb038cf9241e`，`/health` 回 HTTP 200；`tools/list` 回 HTTP 200，列出 `parse_trip_request`、`validate_trip`、`get_trip`、`get_place_details`、`plan_trip`、`build_trip_site`、`publish_trip_site`。`get_place_details` 單次唯讀查詢回 HTTP 200、`available`，署名 `Google Maps`，不保存回應內容。一般 ChatGPT Chat 的工具清單需在 app/plugin 詳細資料頁 Refresh apps 後實際核對；Railway 清單不能代替 UI 驗收。實際 ChatGPT 使用者應透過私人 Site Worker 呼叫 MCP，不要把 Railway 後端網址當作公開的 Site Worker 網址。

公開行程頁的即時地點名稱端點由同一服務提供，不需要新增 Railway 變數。它只允許 GitHub Pages 精確來源、registry 中已發布的行程及每日排程內的 Google Place ID；每來源每分鐘最多 60 次，且與 MCP `get_place_details` 共用每月最多 1,000 次 Places Details 請求。月計數只記錄 UTC 月份與總次數，持久放在 `/data/.public-place-details-usage.json`，不記錄 IP、Place ID 或 Google 回應。Page bundle 只含 API 網址，不含 Google key 或 Places 詳細資料；前端請求使用 `no-store`，並附 Google Maps 與第三方 attribution。這些服務端點可能產生 Google Cloud API 費用；月上限只限制經本 Railway 服務路由的用量，不代表整個 GCP 專案不會超過免費額度。

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

`publish_trip_site` 已部署並出現在遠端 `tools/list`。發布前會要求 ChatGPT 使用者明確確認公開；每一天都必須有餐點，日期必須有效，Canonical Trip validation 不可有阻擋 finding。Places 詳細資料在新行程寫入或重新發布時會先移除，只保留原始 Place ID 及使用者自己的行程／筆記；歷史檔案不會自動改寫。住宿可以留空；未提供住宿時，`schedule.hotel_missing` 和 `schedule.origin_unknown` 會保留為未驗證警告，不會因缺住宿本身阻擋發布。相同 bundle 的 registry 缺項或過期時，工具只修復 registry。

（歷史紀錄）截至 2026-10-08 較早時點，PR #230 後的 MCP `tools/list` 當時列出六項工具；其後正式服務已更新至本節上述 runtime source。此段不代表目前工具清單或發布狀態。Places 資料保存規則與歷史資料範圍仍追蹤於 #199。

2026-10-05 的歷史檢查當時尚無 `GITHUB_TOKEN`；其後的設定與權限驗證以本節 2026-10-08 狀態為準。

只核對變數名稱且不顯示值的指令：

```sh
railway variable list --service ai-traveller --environment production --json | jq -r 'if type == "array" then .[] | if type == "object" then ((.name // .key) | strings) else empty end else keys[] end' | sort
```
